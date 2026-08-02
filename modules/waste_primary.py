"""
Conveyor 1 — Primary Segregation.

FIXED: this used to run a cascade (waste_seg2.pt -> crop -> final_7types.pt),
which caused the two models' detections/labels to visually mix and get
confusing on screen. Now it's a plain STANDALONE detector — exactly like
your working test script (`waste_seg.py`) — waste_seg2.pt runs on its own,
draws its own boxes/labels, nothing else. final_7types.pt runs completely
separately on Conveyor 2 (Secondary Plastic Classification / modules/waste.py)
so the two never interfere with each other again.
"""
import os
import csv
import time
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


def _iou(a, b):
    xA, yA = max(a[0], b[0]), max(a[1], b[1])
    xB, yB = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, xB - xA) * max(0, yB - yA)
    if inter == 0:
        return 0
    areaA = (a[2] - a[0]) * (a[3] - a[1])
    areaB = (b[2] - b[0]) * (b[3] - b[1])
    return inter / float(areaA + areaB - inter)


class WastePrimaryProcessor:
    def __init__(self):
        self.model = None
        print(f"[WASTE-PRIMARY] Looking for model at: {config.WASTE_PRIMARY_MODEL}")
        if os.path.exists(config.WASTE_PRIMARY_MODEL):
            self.model = YOLO(config.WASTE_PRIMARY_MODEL)
            print(f"[WASTE-PRIMARY] Model LOADED OK. Classes: {self.model.names}")
        else:
            print("[WASTE-PRIMARY] Model not found — module will show placeholder")

        self.frame_count = 0
        self.session_counts = {}
        self.last_seen = {}
        self.log_path = os.path.join(config.CAPTURES_DIR, "waste_primary_log.csv")
        self._ensure_log()
        self._warmup()

        self._fps_t0 = time.time()
        self._fps_frames = 0
        self.current_fps = 0.0

        # Stable-detection buffer: a box only gets COUNTED/LOGGED once it has
        # matched (by position + label) across 2 consecutive inference passes.
        # This stops single-frame false positives / flicker from inflating
        # counts, while still drawing every box immediately so the live
        # preview stays responsive (no visible lag added).
        self._prev_pass_boxes = []  # [(x1,y1,x2,y2,label), ...] from last inference pass
        self._pending_stable = {}   # label -> consecutive-match streak
        self.last_boxes = []            # for /api/live_boxes (raw-feed overlay)
        self.last_frame_size = (0, 0)

    def _warmup(self):
        """Absorb model-load/first-inference cost at startup, not on the
        first live frame — keeps the stream from stuttering at camera start.
        Applies equally whether the source is a live camera or an uploaded
        video file, since both go through the same processing pipeline."""
        if self.model is None:
            return
        dummy = np.zeros((config.INFER_IMGSZ, config.INFER_IMGSZ, 3), dtype=np.uint8)
        try:
            kwargs = dict(conf=config.WASTE_PRIMARY_CONF, device=config.DEVICE,
                          half=config.USE_FP16, imgsz=config.INFER_IMGSZ, verbose=False)
            if torch is not None:
                with torch.inference_mode():
                    self.model(dummy, **kwargs)
            else:
                self.model(dummy, **kwargs)
            print("[WASTE-PRIMARY] Model warm-up done.")
        except Exception as e:
            print(f"[WASTE-PRIMARY] Warm-up skipped (non-fatal): {e}")

    def _ensure_log(self):
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w", newline="") as f:
                csv.writer(f).writerow(["Timestamp", "Class", "Confidence"])

    def _log_detection(self, label, conf):
        with open(self.log_path, "a", newline="") as f:
            csv.writer(f).writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), label, round(conf, 2)])

    def status(self):
        return {"model_loaded": self.model is not None}

    def process(self, frame):
        if self.model is None:
            cv2.putText(frame, "waste_seg2.pt NOT FOUND in /models", (15, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 140, 255), 2)
            return frame

        self.frame_count += 1
        self._fps_frames += 1
        elapsed = time.time() - self._fps_t0
        if elapsed >= 2.0:
            self.current_fps = self._fps_frames / elapsed
            self._fps_frames = 0
            self._fps_t0 = time.time()

        kwargs = dict(conf=config.WASTE_PRIMARY_CONF, iou=0.45, device=config.DEVICE,
                      half=config.USE_FP16, imgsz=config.INFER_IMGSZ, verbose=False)
        if torch is not None:
            with torch.inference_mode():
                results = self.model(frame, **kwargs)
        else:
            results = self.model(frame, **kwargs)

        current_pass_boxes = []
        any_detection = False

        for r in results:
            names = r.names
            for box in r.boxes:
                any_detection = True
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                label = names.get(cls_id, str(cls_id))
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                color = get_color_for_label(label)

                # Draw immediately every pass — live preview stays responsive,
                # no visible delay added for the stability check below.
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                text = f"{label} {conf:.2f}"
                (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
                cv2.rectangle(frame, (x1, max(0, y1 - th - 10)), (x1 + tw + 6, y1), color, -1)
                cv2.putText(frame, text, (x1 + 3, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

                current_pass_boxes.append((x1, y1, x2, y2, label, conf))

                # Stable detection: only count/log once this box matches a
                # box from the PREVIOUS inference pass (same label, IOU>0.4) —
                # i.e. it's been seen consistently, not a one-frame flicker.
                matched_prev = any(
                    pl == label and _iou((x1, y1, x2, y2), (px1, py1, px2, py2)) > 0.4
                    for px1, py1, px2, py2, pl, _pc in self._prev_pass_boxes
                )
                if matched_prev:
                    key = label
                    now = time.time()
                    if now - self.last_seen.get(key, 0) > 1.5:
                        self.session_counts[key] = self.session_counts.get(key, 0) + 1
                        self._log_detection(label, conf)
                    self.last_seen[key] = now

        # Side-channel for the fast raw-video + canvas-overlay endpoint (see
        # app.py /raw_feed + /api/live_boxes): frontend can draw these boxes
        # on top of the UNPROCESSED camera stream so the video itself never
        # waits on inference — same principle as the Node/React version.
        self.last_boxes = [
            {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "label": label, "conf": round(conf, 2)}
            for (x1, y1, x2, y2, label, conf) in current_pass_boxes
        ]
        self.last_frame_size = (frame.shape[1], frame.shape[0])

        self._prev_pass_boxes = current_pass_boxes

        h, w = frame.shape[:2]
        if not any_detection:
            cv2.putText(frame, "No waste detected", (15, h - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150, 150, 150), 2)
        cv2.putText(frame, f"FPS: {self.current_fps:.1f}", (w - 110, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        return frame

    def get_counts(self):
        return dict(self.session_counts)

    def reset_counts(self):
        self.session_counts = {}
        self.last_seen = {}
        self._prev_pass_boxes = []
