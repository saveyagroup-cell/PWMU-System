"""
ANPR — High Speed Real-Time Number Plate Recognition
YOLOv8 + EasyOCR + Multi-Frame Voting, LIVE plate display.

Unlike the earlier version, the plate text now appears in GREEN as soon as
ANY OCR reading comes back for that box — you don't have to wait for full
multi-frame confirmation to *see* something. The multi-frame voting still
runs underneath and decides what actually gets SAVED to Supabase/CSV (so
saved records are still reliable), but the live video feed itself feels
much more responsive.
"""
import os
import re
import cv2
import csv
import time
import queue
import threading
import numpy as np
from datetime import datetime
from collections import Counter
from ultralytics import YOLO

import config
from modules import supabase_client

try:
    import torch
except ImportError:
    torch = None

_reader = None
PLATE_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def _get_reader():
    global _reader
    if _reader is None:
        import easyocr
        gpu = config.DEVICE.startswith("cuda")
        _reader = easyocr.Reader(['en'], gpu=gpu)
        print(f"[PLATE] EasyOCR loaded (GPU={gpu})")
    return _reader


def _levenshtein(a, b):
    if len(a) < len(b):
        a, b = b, a
    if len(b) == 0:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        current = [i + 1]
        for j, cb in enumerate(b):
            current.append(min(previous[j + 1] + 1, current[j] + 1, previous[j] + (ca != cb)))
        previous = current
    return previous[-1]


def _iou(boxA, boxB):
    xA, yA = max(boxA[0], boxB[0]), max(boxA[1], boxB[1])
    xB, yB = min(boxA[2], boxB[2]), min(boxA[3], boxB[3])
    inter = max(0, xB - xA) * max(0, yB - yA)
    if inter == 0:
        return 0
    areaA = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    areaB = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    return inter / float(areaA + areaB - inter)


def _clean_hsrp_noise(text):
    if text.startswith("IND") and len(text) > 3:
        text = text[3:]
    if text.endswith("IND") and len(text) > 3:
        text = text[:-3]
    return text


def _is_valid_plate_shape(x1, y1, x2, y2):
    width, height = x2 - x1, y2 - y1
    if width <= 0 or height <= 0:
        return False
    ratio = width / height
    if ratio < config.PLATE_MIN_ASPECT_RATIO or ratio > config.PLATE_MAX_ASPECT_RATIO:
        return False
    if width * height < config.PLATE_MIN_BOX_AREA:
        return False
    return True


class PlateProcessor:
    def __init__(self):
        if os.path.exists(config.PLATE_MODEL):
            self.model = YOLO(config.PLATE_MODEL)
            print(f"[PLATE] Model loaded: {config.PLATE_MODEL}")
            print(f"[PLATE] Classes: {self.model.names}")
        else:
            self.model = None
            print(f"[PLATE] Model NOT found: {config.PLATE_MODEL}")

        self.frame_count = 0
        self.last_saved = {}
        self.recent_plates = []
        self.saved_plate_texts = []
        self.log_path = os.path.join(config.CAPTURES_DIR, "detected_plates.csv")

        self.tracks = {}
        self._next_track_id = 0

        self._ensure_log()
        self._warmup()

        # ---- Async OCR thread ----------------------------------------
        # OCR (EasyOCR) is the slowest part (~150-400ms per call on CPU).
        # Running it synchronously inside process() blocks the entire video
        # pipeline.  Instead we put (track_id, crop) items in a work queue
        # and a background thread calls EasyOCR independently.  The video
        # frame is drawn immediately with whatever text the track already has
        # (cached from the previous OCR result), so the stream is NEVER
        # blocked waiting for OCR to finish.
        self._ocr_work_q = queue.Queue(maxsize=8)   # capped so backlog can't build up
        self._ocr_result_q = queue.Queue()
        self._ocr_thread = threading.Thread(target=self._ocr_worker, daemon=True)
        self._ocr_thread.start()
        print("[PLATE] Async OCR thread started.")

    def get_recent(self):
        return list(self.recent_plates)

    def reset(self):
        self.recent_plates = []
        self.saved_plate_texts = []
        self.last_saved = {}
        self.tracks = {}
        self._next_track_id = 0

    def _ensure_log(self):
        if os.path.exists(self.log_path):
            return
        with open(self.log_path, "w", newline="") as f:
            csv.writer(f).writerow(["Date", "Time", "Plate Number", "Confidence",
                                     "Vehicle_Type", "Direction", "Source", "ImageURL"])

    def _warmup(self):
        if self.model is None:
            return
        dummy = np.zeros((config.INFER_IMGSZ, config.INFER_IMGSZ, 3), dtype=np.uint8)
        kwargs = dict(conf=config.PLATE_CONF, device=config.DEVICE, half=config.USE_FP16,
                      imgsz=config.INFER_IMGSZ, verbose=False)
        try:
            if torch is not None:
                with torch.inference_mode():
                    self.model.predict(source=dummy, **kwargs)
            else:
                self.model.predict(source=dummy, **kwargs)
            print("[PLATE] Warm-up done")
        except Exception as e:
            print(f"[PLATE] Warm-up failed (non-fatal): {e}")

    # ---- Async OCR worker (runs in background thread) ----
    def _ocr_worker(self):
        """Background daemon: pops (tid, crop) from work queue, runs OCR,
        puts (tid, candidates) in result queue. Never blocks the main thread."""
        while True:
            try:
                tid, crop = self._ocr_work_q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                candidates = self._run_ocr_on_crop(crop)
                self._ocr_result_q.put((tid, candidates))
            except Exception as e:
                print(f"[PLATE] OCR worker error: {e}")

    def _submit_ocr(self, track_id, crop):
        """Non-blocking: put crop in OCR queue, drop if queue is full
        (better to skip one frame than to let the backlog grow)."""
        try:
            self._ocr_work_q.put_nowait((track_id, crop))
        except queue.Full:
            pass   # queue full → skip this frame's OCR, use cached text

    def _drain_ocr_results(self):
        """Collect any OCR results the worker thread has finished.
        Called once per process() frame — non-blocking."""
        while not self._ocr_result_q.empty():
            try:
                tid, candidates = self._ocr_result_q.get_nowait()
                if tid in self.tracks and candidates:
                    track = self.tracks[tid]
                    track["votes"].extend(candidates)
                    best_text, best_conf = max(candidates, key=lambda x: x[1])
                    # Only update live text if this is a better read
                    if best_conf > track.get("live_conf", 0):
                        track["live_text"] = best_text
                        track["live_conf"] = best_conf
            except queue.Empty:
                break

    @staticmethod
    def _preprocess_for_ocr(crop):
        """Return a SINGLE preprocessed image for OCR.
        Brightness-adaptive: pick the ONE variant most likely to work
        instead of always running 2-3 passes.
        """
        h, w = crop.shape[:2]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

        # Adaptive scaling: only upscale small/far plates
        if h < 40:
            scale = 3.0
        elif h < 70:
            scale = 1.8
        else:
            scale = 1.0
        if scale != 1.0:
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        # Hard size cap — smaller = much faster OCR (quadratic scaling)
        max_dim = config.PLATE_OCR_MAX_DIM
        gh, gw = gray.shape[:2]
        if max(gh, gw) > max_dim:
            ratio = max_dim / max(gh, gw)
            gray = cv2.resize(gray, None, fx=ratio, fy=ratio, interpolation=cv2.INTER_AREA)

        # Choose ONE preprocessing variant based on brightness
        if config.PLATE_OCR_SINGLE_VARIANT:
            mean_brightness = float(np.mean(gray))
            if mean_brightness < 80:
                # Dark/night plate: CLAHE brings out detail
                result = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8)).apply(gray)
            elif mean_brightness > 170:
                # Bright/washed plate: adaptive threshold cuts glare
                result = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                               cv2.THRESH_BINARY, 31, 15)
            else:
                # Normal: use gray directly (no extra processing needed)
                result = gray
            return [result]
        else:
            # Multi-variant fallback (slower but more thorough)
            adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                             cv2.THRESH_BINARY, 31, 15)
            clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8)).apply(gray)
            return [adaptive, clahe]

    def _run_ocr_on_crop(self, crop):
        """Blocking OCR call — always runs in the background thread, never
        in the main video pipeline. Returns list of (text, conf) candidates."""
        if crop is None or crop.size == 0:
            return []
        variants = self._preprocess_for_ocr(crop)
        reader = _get_reader()
        candidates = []
        for img in variants:
            results = reader.readtext(img, allowlist=PLATE_CHARS, detail=1, paragraph=False)
            for result in results:
                try:
                    _, text, conf = result
                    text = re.sub(r"[^A-Z0-9]", "", text.upper())
                    text = _clean_hsrp_noise(text)
                    if 4 <= len(text) <= 10 and conf >= config.PLATE_MIN_OCR_CONF:
                        candidates.append((text, float(conf)))
                except Exception:
                    continue
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates

    @staticmethod
    def _char_level_vote(votes, min_frames):
        if len(votes) < min_frames:
            return "", 0.0, False
        length_counter = Counter(len(t) for t, c in votes)
        target_length, target_count = length_counter.most_common(1)[0]
        if target_count / len(votes) < config.PLATE_MIN_VOTE_AGREEMENT:
            return "", 0.0, False

        filtered = [(t, c) for t, c in votes if len(t) == target_length]
        final_chars = []
        for i in range(target_length):
            weights = {}
            for text, conf in filtered:
                weights[text[i]] = weights.get(text[i], 0) + conf
            total = sum(weights.values())
            best_char = max(weights, key=weights.get)
            if (weights[best_char] / total) < config.PLATE_MIN_VOTE_AGREEMENT:
                return "", 0.0, False
            final_chars.append(best_char)

        final_text = "".join(final_chars)
        avg_conf = sum(c for t, c in filtered) / len(filtered)
        return final_text, avg_conf, True

    def _try_confirm(self, track):
        votes = track["votes"]
        if not votes:
            return "", 0.0, False

        if len(votes) >= config.PLATE_MIN_VOTE_FRAMES_EARLY:
            recent = votes[-config.PLATE_MIN_VOTE_FRAMES_EARLY:]
            texts = set(t for t, c in recent)
            if len(texts) == 1:
                text = list(texts)[0]
                avg_conf = sum(c for t, c in recent) / len(recent)
                if avg_conf >= config.PLATE_EARLY_CONFIRM_MIN_CONF:
                    return text, avg_conf, True

        # LIVE display always reflects the best guess so far, even unconfirmed
        best_live = max(votes, key=lambda x: x[1])
        track["live_text"], track["live_conf"] = best_live[0], best_live[1]

        final_text, final_conf, confirmed = self._char_level_vote(votes, config.PLATE_MAX_VOTE_FRAMES)
        if confirmed:
            track["live_text"], track["live_conf"] = final_text, final_conf
        return final_text, final_conf, confirmed

    def _match_track(self, box):
        best_id, best_iou = None, config.PLATE_IOU_MATCH_THRESH
        for tid, t in self.tracks.items():
            score = _iou(box, t["box"])
            if score > best_iou:
                best_id, best_iou = tid, score
        if best_id is not None:
            return best_id
        tid = self._next_track_id
        self._next_track_id += 1
        self.tracks[tid] = {"box": box, "votes": [], "last_seen": time.time(), "first_seen": time.time(),
                             "live_text": "", "live_conf": 0.0, "saved_text": None, "final_text": "",
                             "last_crop": None, "unconfirmed_saved": False}
        return tid

    def _cleanup_tracks(self):
        now = time.time()
        stale = [tid for tid, t in self.tracks.items() if now - t["last_seen"] > config.PLATE_TRACK_TIMEOUT]
        for tid in stale:
            t = self.tracks[tid]
            if t["saved_text"] is None and not t["unconfirmed_saved"] and t["last_crop"] is not None:
                self._save_unconfirmed(t)
            del self.tracks[tid]

    def _is_duplicate(self, plate_text):
        for saved in self.saved_plate_texts:
            max_len = max(len(saved), len(plate_text))
            if max_len == 0:
                continue
            if (1 - _levenshtein(saved, plate_text) / max_len) >= config.PLATE_SIMILARITY_THRESHOLD:
                return True
        return False

    def _save_unconfirmed(self, track):
        best_guess, best_conf = "", 0.0
        if track["votes"]:
            best_guess, best_conf = max(track["votes"], key=lambda x: x[1])
        if not best_guess:
            best_guess = "UNREADABLE"
        track["unconfirmed_saved"] = True
        self._save_detection(best_guess, best_conf, track["last_crop"], confirmed=False)

    def _save_detection(self, plate_text, ocr_conf, crop, confirmed, vehicle_type="—", direction="—", source="auto"):
        now = datetime.now()
        now_ts = now.timestamp()
        dedupe_key = plate_text if confirmed else "unconfirmed"

        if source == "auto" and dedupe_key in self.last_saved and \
                (now_ts - self.last_saved[dedupe_key]) < config.PLATE_SAVE_COOLDOWN:
            return
        if confirmed and self._is_duplicate(plate_text):
            print(f"[PLATE] Duplicate skipped: {plate_text}")
            return
        self.last_saved[dedupe_key] = now_ts

        image_url = None
        if crop is not None and crop.size > 0:
            local_path = os.path.join(config.CAPTURES_DIR, f"plate_{int(now_ts*1000)}.jpg")
            cv2.imwrite(local_path, crop)
            print(f"[PLATE] Image saved: {local_path}")
            image_url = supabase_client.upload_image(local_path, "plates", bucket=config.SUPABASE_ANPR_BUCKET)
            if image_url:
                print(f"[PLATE] Uploaded: {image_url}")
            elif supabase_client.is_enabled():
                print("[PLATE] Upload failed — kept locally only")

        with open(self.log_path, "a", newline="") as f:
            csv.writer(f).writerow([now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), plate_text,
                                     round(float(ocr_conf), 2), vehicle_type, direction, source, image_url or ""])

        supabase_client.insert_row("plate_detections", {
            "plate_number": plate_text, "confidence": round(float(ocr_conf), 2),
            "image_url": image_url, "detected_at": now.isoformat(),
        })

        if confirmed:
            self.saved_plate_texts.append(plate_text)

        entry = {"plate": plate_text, "conf": round(float(ocr_conf), 2), "time": now.strftime("%H:%M:%S"),
                  "url": image_url, "vehicle_type": vehicle_type, "direction": direction,
                  "source": source, "confirmed": confirmed}
        self.recent_plates.insert(0, entry)
        self.recent_plates = self.recent_plates[:15]

    def manual_entry(self, plate_text, vehicle_type="—", direction="—"):
        plate_text = "".join(c for c in plate_text if c.isalnum()).upper() or "UNKNOWN"
        self._save_detection(plate_text, 1.0, None, confirmed=True, vehicle_type=vehicle_type,
                              direction=direction, source="manual")

    def process(self, frame, vehicle_context=None):
        if self.model is None:
            cv2.putText(frame, "number_plate.pt NOT FOUND", (20, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            return frame

        vtype = vehicle_context.get("vehicle_type", "—") if vehicle_context else "—"
        direction = vehicle_context.get("direction", "—") if vehicle_context else "—"

        self.frame_count += 1
        h, w = frame.shape[:2]

        # --- Step 1: collect any OCR results the background thread finished ---
        # Non-blocking: immediately returns if no results are ready yet.
        self._drain_ocr_results()

        kwargs = dict(conf=config.PLATE_CONF, device=config.DEVICE, half=config.USE_FP16,
                      imgsz=config.INFER_IMGSZ, verbose=False)
        if torch is not None:
            with torch.inference_mode():
                results = self.model.predict(source=frame, **kwargs)
        else:
            results = self.model.predict(source=frame, **kwargs)

        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)
                if not _is_valid_plate_shape(x1, y1, x2, y2):
                    continue

                tid = self._match_track((x1, y1, x2, y2))
                track = self.tracks[tid]
                track["box"] = (x1, y1, x2, y2)
                track["last_seen"] = time.time()

                if track["saved_text"]:
                    # Already confirmed — draw and skip all OCR
                    self._draw_box(frame, x1, y1, x2, y2, track["final_text"], tid, confirmed=True)
                    continue

                crop = frame[y1:y2, x1:x2]
                if crop.size == 0:
                    continue
                track["last_crop"] = crop.copy()

                # --- Step 2: submit crop for async OCR (non-blocking) ---
                # Only submit if we haven't already collected enough votes.
                # This avoids flooding the queue when a plate stays visible.
                enough_votes = len(track["votes"]) >= config.PLATE_MAX_VOTE_FRAMES
                if not enough_votes:
                    self._submit_ocr(tid, crop.copy())

                # --- Step 3: draw with whatever text we have right now ---
                # The OCR result may arrive on the NEXT frame — that's fine.
                # Live text is updated by _drain_ocr_results() at frame start.
                final_text, final_conf, confirmed = self._try_confirm(track)

                display_text = final_text if confirmed else track["live_text"]
                self._draw_box(frame, x1, y1, x2, y2, display_text, tid, confirmed or bool(display_text))

                if confirmed and len(final_text) >= config.PLATE_MIN_LEN:
                    track["saved_text"] = final_text
                    track["final_text"] = final_text
                    self._save_detection(final_text, final_conf, crop, confirmed=True,
                                          vehicle_type=vtype, direction=direction)
                else:
                    reading_time = time.time() - track["first_seen"]
                    if reading_time >= config.PLATE_READING_TIMEOUT and not track["unconfirmed_saved"]:
                        track["unconfirmed_saved"] = True
                        self._save_detection("UNREADABLE", track.get("live_conf", 0), crop, confirmed=False,
                                              vehicle_type=vtype, direction=direction)


        self._cleanup_tracks()
        return frame

    @staticmethod
    def _draw_box(frame, x1, y1, x2, y2, text, track_id, confirmed):
        GREEN, ORANGE = (0, 255, 0), (0, 165, 255)
        color = GREEN if text else ORANGE
        label = text if text else "Detecting..."
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.75, 2)
        label_y = max(y1 - th - 12, 0)
        cv2.rectangle(frame, (x1, label_y), (x1 + tw + 12, y1), color, -1)
        cv2.putText(frame, label, (x1 + 6, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 0), 2, cv2.LINE_AA)
