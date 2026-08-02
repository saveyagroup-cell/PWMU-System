"""
Conveyor 2 — Secondary Plastic Classification (7 RIC Types).

Runs ONLY final_7types.pt (PET, HDPE, PVC, LDPE, PP, PS, OTHER).
This module is 100% standalone — it NEVER touches waste_seg2.pt
and has zero dependency on waste_primary.py. The two processors
can run simultaneously on the same camera or different cameras
without interfering with each other.

Upgrades vs original:
  - ByteTrack (model.track) → each item gets a persistent track_id,
    so the same bottle is never double-counted across frames.
  - imgsz=480 (was 320) → better far-field / small-object detection.
  - Frame-skip reused from config.FRAME_SKIP → stream stays smooth on CPU.
  - FPS counter (same as waste_primary.py).
  - Detection timeline log → per-minute counts for the dashboard chart.
  - RIC metadata (full name, recyclability, color) exposed via get_ric_info().
"""
import os
import csv
import time
from collections import defaultdict, deque
from datetime import datetime

import cv2
import numpy as np
from ultralytics import YOLO
import config
from modules.colors import get_color_for_label

try:
    import torch
except Exception:
    torch = None


# ---------------------------------------------------------------------------
# 7-type RIC metadata (mirrors config.PLASTIC_RIC_INFO but kept local so the
# module stays self-contained and doesn't break if config isn't updated yet).
# ---------------------------------------------------------------------------
_PLASTIC_INFO = {
    "PET":   {"ric": 1, "full": "PET — Type 1",   "recyclable": True,  "color": "#3B82F6"},
    "HDPE":  {"ric": 2, "full": "HDPE — Type 2",  "recyclable": True,  "color": "#10B981"},
    "PVC":   {"ric": 3, "full": "PVC — Type 3",   "recyclable": False, "color": "#EF4444"},
    "LDPE":  {"ric": 4, "full": "LDPE — Type 4",  "recyclable": True,  "color": "#F59E0B"},
    "PP":    {"ric": 5, "full": "PP — Type 5",    "recyclable": True,  "color": "#8B5CF6"},
    "PS":    {"ric": 6, "full": "PS — Type 6",    "recyclable": False, "color": "#EC4899"},
    "OTHER": {"ric": 7, "full": "Other — Type 7", "recyclable": False, "color": "#6B7280"},
}

# Map raw model class names (mixed-case, legacy aliases) → canonical RIC key.
# The current final_7types.pt uses: HDPE, LDPE, OTHERS, PET, PVC, Polypropylene, Polystyrene
_LABEL_NORMALIZER = {
    # Exact matches (already canonical)
    "PET": "PET", "HDPE": "HDPE", "PVC": "PVC", "LDPE": "LDPE",
    "PP":  "PP",  "PS":   "PS",   "OTHER": "OTHER",
    # Legacy / mixed-case model outputs
    "POLYPROPYLENE": "PP",
    "Polypropylene": "PP",
    "POLYSTYRENE":   "PS",
    "Polystyrene":   "PS",
    "OTHERS":        "OTHER",
    "Others":        "OTHER",
}


def _normalize_label(raw_label: str) -> str:
    """Map whatever the model outputs to a canonical 7-type RIC key."""
    return _LABEL_NORMALIZER.get(raw_label) or _LABEL_NORMALIZER.get(raw_label.upper(), raw_label.upper())

# Fallback colors for labels not in the dict
_DEFAULT_COLORS = ["#3B82F6", "#10B981", "#F59E0B", "#8B5CF6", "#EC4899", "#EF4444", "#6B7280"]


def _iou(a, b):
    xA, yA = max(a[0], b[0]), max(a[1], b[1])
    xB, yB = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, xB - xA) * max(0, yB - yA)
    if inter == 0:
        return 0
    areaA = (a[2] - a[0]) * (a[3] - a[1])
    areaB = (b[2] - b[0]) * (b[3] - b[1])
    return inter / float(areaA + areaB - inter)


class WasteProcessor:
    """
    Standalone 7-type plastic classifier — runs ONLY final_7types.pt.

    Key design decisions:
    - Uses model.track() (ByteTrack) so each physical item keeps a stable
      track_id. Counting is done per track_id — the same item only adds to
      session_counts once, however many frames it stays visible.
    - Frame-skip: YOLO only runs every config.FRAME_SKIP frames; raw video
      is always pushed to raw_frame_queue so the browser preview is smooth.
    - imgsz=480 gives ~30% better recall on far/small objects vs 320,
      at roughly the same CPU cost (vs 640 which is 2x heavier).
    """

    def __init__(self):
        self.model = None
        self._load_model()

        self.frame_count = 0
        self.session_counts = {}       # label → count (unique track IDs seen)
        self._counted_track_ids = {}   # label → set of track_ids already counted
        self._last_track_labels = {}   # track_id → label (for when track exits)
        self._last_seen_time = {}      # label → timestamp (for fallback counting)

        self.log_path = os.path.join(config.CAPTURES_DIR, "waste_secondary_log.csv")
        self._ensure_log()
        self._warmup()

        # FPS tracking
        self._fps_t0 = time.time()
        self._fps_frames = 0
        self.current_fps = 0.0

        # Live-boxes for /api/live_boxes canvas overlay
        self.last_boxes = []
        self.last_frame_size = (0, 0)
        self._prev_pass_boxes = []   # kept for IOU-based fallback if tracking off

        # Detection timeline: deque of (epoch_second, label) for last 10 min
        # Used by /api/detection_timeline to build the per-minute chart.
        self._timeline_log = deque(maxlen=6000)   # 10 min × 10 det/sec max

        # Recent alert feed: last 20 detections with timestamp + conf
        self._recent_alerts = deque(maxlen=20)

        print(f"[WASTE-SECONDARY] Init done. ByteTrack={'ON' if config.WASTE_SECONDARY_USE_TRACK else 'OFF'}, "
              f"imgsz={config.WASTE_SECONDARY_IMGSZ}, conf={config.WASTE_SECONDARY_CONF}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_model(self):
        """Load ONLY final_7types.pt — no cascade/secondary model."""
        model_path = config.WASTE_MATERIAL_MODEL
        print(f"[WASTE-SECONDARY] Looking for model at: {model_path}")
        if os.path.exists(model_path):
            self.model = YOLO(model_path)
            print(f"[WASTE-SECONDARY] Model LOADED OK. Classes: {self.model.names}")
        else:
            print(f"[WASTE-SECONDARY] Model NOT FOUND at {model_path} — module will show placeholder")

    def _warmup(self):
        """Absorb first-frame latency at startup."""
        if self.model is None:
            return
        dummy = np.zeros((config.WASTE_SECONDARY_IMGSZ, config.WASTE_SECONDARY_IMGSZ, 3), dtype=np.uint8)
        kwargs = dict(
            conf=config.WASTE_SECONDARY_CONF,
            device=config.DEVICE,
            half=config.USE_FP16,
            imgsz=config.WASTE_SECONDARY_IMGSZ,
            verbose=False,
        )
        try:
            if torch is not None:
                with torch.inference_mode():
                    self.model(dummy, **kwargs)
            else:
                self.model(dummy, **kwargs)
            print("[WASTE-SECONDARY] Model warm-up done.")
        except Exception as e:
            print(f"[WASTE-SECONDARY] Warm-up skipped (non-fatal): {e}")

    def _ensure_log(self):
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w", newline="") as f:
                csv.writer(f).writerow(["Timestamp", "Class", "Confidence", "TrackID"])

    def _log_detection(self, label, conf, track_id=None):
        with open(self.log_path, "a", newline="") as f:
            csv.writer(f).writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                label, round(conf, 2), track_id or ""
            ])

    def _get_color(self, label):
        """Return consistent hex color for a label."""
        info = _PLASTIC_INFO.get(label.upper())
        if info:
            return info["color"]
        # Fallback: use colors module or cycle through defaults
        return get_color_for_label(label)

    def _hex_to_bgr(self, hex_color):
        """Convert '#RRGGBB' → (B, G, R) for OpenCV."""
        try:
            h = hex_color.lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            return (b, g, r)
        except Exception:
            return (200, 200, 200)

    def _update_fps(self):
        self._fps_frames += 1
        elapsed = time.time() - self._fps_t0
        if elapsed >= 2.0:
            self.current_fps = self._fps_frames / elapsed
            self._fps_frames = 0
            self._fps_t0 = time.time()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def status(self):
        return {"model_loaded": self.model is not None}

    def process(self, frame):
        """
        Run inference on frame, draw boxes in-place, return annotated frame.
        - Uses model.track() when WASTE_SECONDARY_USE_TRACK=True (ByteTrack).
        - Falls back to model() (raw detect) if tracking is disabled.
        - Runs YOLO every config.FRAME_SKIP frames; between frames the last
          annotated boxes are re-drawn on the fresh frame (no stale video).
        """
        if self.model is None:
            cv2.putText(frame, "final_7types.pt NOT FOUND in /models", (15, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 140, 255), 2)
            return frame

        self.frame_count += 1
        self._update_fps()

        # Frame-skip: only run YOLO every Nth frame
        run_inference = (self.frame_count % max(config.FRAME_SKIP, 1) == 0) or (self.frame_count == 1)

        kwargs = dict(
            conf=config.WASTE_SECONDARY_CONF,
            iou=config.WASTE_SECONDARY_IOU,
            device=config.DEVICE,
            half=config.USE_FP16,
            imgsz=config.WASTE_SECONDARY_IMGSZ,
            verbose=False,
            # agnostic_nms: treats all classes as one during NMS so a PET box
            # and an HDPE box at the same location are suppressed to ONE winner.
            agnostic_nms=config.WASTE_SECONDARY_AGNOSTIC_NMS,
        )
        if config.WASTE_SECONDARY_AUGMENT and config.DEVICE != "cpu":
            kwargs["augment"] = True

        # --- ROI crop (optional) ---
        # If WASTE_SECONDARY_ROI is set, crop the frame to belt-area only
        # before sending it to YOLO. Coordinates are offset back to full-frame
        # when drawing boxes so the overlay still lines up with /raw_feed.
        h_full, w_full = frame.shape[:2]
        roi = config.WASTE_SECONDARY_ROI
        if roi is not None:
            rx1 = int(roi[0] * w_full); ry1 = int(roi[1] * h_full)
            rx2 = int(roi[2] * w_full); ry2 = int(roi[3] * h_full)
            infer_frame = frame[ry1:ry2, rx1:rx2]
            roi_offset = (rx1, ry1)
        else:
            infer_frame = frame
            roi_offset = (0, 0)

        if run_inference:
            try:
                if config.WASTE_SECONDARY_USE_TRACK:
                    # ByteTrack: persist=True keeps the tracker state across calls
                    if torch is not None:
                        with torch.inference_mode():
                            results = self.model.track(infer_frame, persist=True, tracker="bytetrack.yaml", **kwargs)
                    else:
                        results = self.model.track(infer_frame, persist=True, tracker="bytetrack.yaml", **kwargs)
                else:
                    if torch is not None:
                        with torch.inference_mode():
                            results = self.model(infer_frame, **kwargs)
                    else:
                        results = self.model(infer_frame, **kwargs)
            except Exception as e:
                # bytetrack.yaml not found → graceful fallback to raw detect
                print(f"[WASTE-SECONDARY] Tracking fallback to raw detect: {e}")
                try:
                    if torch is not None:
                        with torch.inference_mode():
                            results = self.model(infer_frame, **kwargs)
                    else:
                        results = self.model(infer_frame, **kwargs)
                except Exception as e2:
                    print(f"[WASTE-SECONDARY] Inference error: {e2}")
                    return frame

            current_pass_boxes = []
            any_detection = False
            now_epoch = time.time()

            for r in results:
                names = r.names
                boxes_data = r.boxes

                for box in boxes_data:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    raw_label = names.get(cls_id, str(cls_id))
                    label = _normalize_label(raw_label)   # Polypropylene→PP, OTHERS→OTHER, etc.
                    # Coordinates are relative to infer_frame (ROI crop); add
                    # roi_offset to get back to full-frame pixel positions.
                    x1 = int(box.xyxy[0][0]) + roi_offset[0]
                    y1 = int(box.xyxy[0][1]) + roi_offset[1]
                    x2 = int(box.xyxy[0][2]) + roi_offset[0]
                    y2 = int(box.xyxy[0][3]) + roi_offset[1]

                    # --- Minimum box area filter ---
                    # Skip detections that are too small to be real items
                    # (far-away noise, reflections, etc.)
                    box_area = max(0, x2 - x1) * max(0, y2 - y1)
                    if box_area < config.WASTE_SECONDARY_MIN_BOX_AREA:
                        continue

                    any_detection = True

                    # Track ID (None if not using ByteTrack or tracker not assigned yet)
                    track_id = None
                    if box.id is not None:
                        try:
                            track_id = int(box.id[0])
                        except Exception:
                            track_id = None

                    # Color from RIC metadata
                    hex_color = self._get_color(label)
                    bgr = self._hex_to_bgr(hex_color)

                    # Draw bounding box
                    cv2.rectangle(frame, (x1, y1), (x2, y2), bgr, 2)

                    # Label badge
                    display_text = f"{label} {conf:.2f}"
                    if track_id is not None:
                        display_text += f" #{track_id}"
                    (tw, th), _ = cv2.getTextSize(display_text, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 2)
                    cv2.rectangle(frame, (x1, max(0, y1 - th - 10)), (x1 + tw + 6, y1), bgr, -1)
                    cv2.putText(frame, display_text, (x1 + 3, y1 - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 2)

                    current_pass_boxes.append({
                        "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                        "label": label, "conf": round(conf, 2),
                        "track_id": track_id,
                        "color": hex_color,
                    })

                    # --- Counting logic ---
                    if track_id is not None:
                        # ByteTrack mode: count each unique track_id once per label
                        seen_ids = self._counted_track_ids.setdefault(label, set())
                        if track_id not in seen_ids:
                            seen_ids.add(track_id)
                            self.session_counts[label] = self.session_counts.get(label, 0) + 1
                            self._log_detection(label, conf, track_id)
                            self._timeline_log.append((now_epoch, label))
                            self._recent_alerts.appendleft({
                                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "label": label,
                                "conf": round(conf, 2),
                                "track_id": track_id,
                                "status": "Verified" if conf >= 0.55 else "Low Conf",
                            })
                    else:
                        # Fallback (no track_id): time-gated counting per label
                        last_seen = self._last_seen_time.get(label, 0)
                        # 1.5 seconds cooldown to avoid double counting the same untracked item
                        if now_epoch - last_seen > 1.5:
                            self.session_counts[label] = self.session_counts.get(label, 0) + 1
                            self._last_seen_time[label] = now_epoch
                            self._log_detection(label, conf, "fallback")
                            self._timeline_log.append((now_epoch, label))
                            self._recent_alerts.appendleft({
                                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "label": label,
                                "conf": round(conf, 2),
                                "track_id": "Un-Tracked",
                                "status": "Verified" if conf >= 0.55 else "Low Conf",
                            })

            self._prev_pass_boxes = current_pass_boxes
            self.last_boxes = current_pass_boxes
            self.last_frame_size = (frame.shape[1], frame.shape[0])

        else:
            # Non-inference frame: re-draw last boxes on fresh frame
            any_detection = bool(self._prev_pass_boxes)
            for b in self._prev_pass_boxes:
                x1, y1, x2, y2 = b["x1"], b["y1"], b["x2"], b["y2"]
                label, conf = b["label"], b["conf"]
                track_id = b.get("track_id")
                bgr = self._hex_to_bgr(b.get("color", "#888888"))

                cv2.rectangle(frame, (x1, y1), (x2, y2), bgr, 2)
                display_text = f"{label} {conf:.2f}"
                if track_id is not None:
                    display_text += f" #{track_id}"
                (tw, th), _ = cv2.getTextSize(display_text, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 2)
                cv2.rectangle(frame, (x1, max(0, y1 - th - 10)), (x1 + tw + 6, y1), bgr, -1)
                cv2.putText(frame, display_text, (x1 + 3, y1 - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 2)

        # HUD overlays
        h, w = frame.shape[:2]
        cv2.putText(frame, "SECONDARY PLASTIC CLASSIFICATION", (15, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 200, 255), 2)
        cv2.putText(frame, f"FPS: {self.current_fps:.1f}", (w - 115, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 255, 0), 2)

        mode_label = "BYTETRACK" if config.WASTE_SECONDARY_USE_TRACK else "DETECT"
        cv2.putText(frame, mode_label, (15, 52),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 180, 60), 1)

        if not any_detection:
            cv2.putText(frame, "No plastic detected", (15, h - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150, 150, 150), 2)

        return frame

    def get_counts(self):
        return dict(self.session_counts)

    def get_track_stats(self):
        """Per-label: how many unique track IDs were seen this session."""
        return {label: len(ids) for label, ids in self._counted_track_ids.items()}

    def get_recent_alerts(self, limit=20):
        """Last N detection events (newest first) for the alert feed."""
        return list(self._recent_alerts)[:limit]

    def get_detection_timeline(self, minutes=10):
        """
        Returns per-minute detection counts for the last `minutes` minutes.
        Format: {"labels": [...], "minutes": ["HH:MM", ...], "series": {label: [count, ...]}}
        """
        now = time.time()
        cutoff = now - minutes * 60

        # Bucket by minute
        buckets = defaultdict(lambda: defaultdict(int))
        for epoch, label in self._timeline_log:
            if epoch < cutoff:
                continue
            minute_key = datetime.fromtimestamp(epoch).strftime("%H:%M")
            buckets[minute_key][label] += 1

        # Build sorted minute slots
        all_minutes = sorted(buckets.keys())
        all_labels = sorted(self.session_counts.keys())

        series = {label: [buckets[m].get(label, 0) for m in all_minutes]
                  for label in all_labels}

        return {"labels": all_labels, "minutes": all_minutes, "series": series}

    def get_ric_info(self):
        """Return RIC metadata dict for all 7 types — used by the dashboard UI."""
        return dict(_PLASTIC_INFO)

    def reset_counts(self):
        self.session_counts = {}
        self._counted_track_ids = {}
        self._prev_pass_boxes = []
        self.last_boxes = []
        self._timeline_log.clear()
        self._recent_alerts.clear()
        print("[WASTE-SECONDARY] Counts reset.")
