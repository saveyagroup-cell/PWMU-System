import csv
import os
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

VEHICLE_LABELS = {1: "Bicycle", 2: "Car", 3: "Motorbike", 5: "Bus", 7: "Truck"}


class _NullContext:
    """No-op context manager fallback when torch isn't importable."""
    def __enter__(self): return self
    def __exit__(self, *a): return False


class VehicleProcessor:
    def __init__(self):
        self.model = YOLO(config.VEHICLE_MODEL)
        self.count_in = 0
        self.count_out = 0
        self.history = {}
        self.line_y = None
        self.log_path = os.path.join(config.CAPTURES_DIR, "vehicle_log.csv")
        self.last_event = None  # {"direction", "vehicle_type", "time"} — for Gate/ANPR correlation
        self._ensure_log()
        self._warmup()

    def _warmup(self):
        """Dummy predict() (NOT track(), so tracker/persist state stays clean)
        at load time — absorbs CUDA/cuDNN + first-run JIT warm-up cost before
        the live stream starts, so the first camera frames don't stutter."""
        dummy = np.zeros((config.INFER_IMGSZ, config.INFER_IMGSZ, 3), dtype=np.uint8)
        ctx = torch.inference_mode() if torch is not None else _NullContext()
        with ctx:
            self.model.predict(dummy, classes=config.VEHICLE_CLASSES, conf=config.VEHICLE_CONF, verbose=False,
                                device=config.DEVICE, half=config.USE_FP16, imgsz=config.INFER_IMGSZ)
        print("[VEHICLE] Model warm-up done.")

    def _ensure_log(self):
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w", newline="") as f:
                csv.writer(f).writerow(["Timestamp", "Direction", "Vehicle_Type", "Vehicle_ID", "Total_IN", "Total_OUT"])

    def reset(self):
        self.count_in = 0
        self.count_out = 0
        self.history = {}

    def process(self, frame):
        h, w = frame.shape[:2]
        if self.line_y is None:
            self.line_y = int(h * config.VEHICLE_LINE_Y_RATIO)

        ctx = torch.inference_mode() if torch is not None else _NullContext()
        with ctx:
            results = self.model.track(frame, persist=True, tracker="bytetrack.yaml",
                                        classes=config.VEHICLE_CLASSES, conf=config.VEHICLE_CONF, verbose=False,
                                        device=config.DEVICE, half=config.USE_FP16,
                                        imgsz=config.INFER_IMGSZ)

        if results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy().astype(int)
            ids = results[0].boxes.id.cpu().numpy().astype(int)
            clss = results[0].boxes.cls.cpu().numpy().astype(int)

            for box, vid, cls_id in zip(boxes, ids, clss):
                x1, y1, x2, y2 = box
                y_center = int((y1 + y2) / 2)
                vtype = VEHICLE_LABELS.get(int(cls_id), "Vehicle")

                if vid not in self.history:
                    self.history[vid] = y_center
                prev_y = self.history[vid]
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                if prev_y < self.line_y <= y_center:
                    self.count_in += 1
                    self._log(now, "IN", vtype, vid)
                    self.last_event = {"direction": "IN", "vehicle_type": vtype, "time": time.time()}
                elif prev_y > self.line_y >= y_center:
                    self.count_out += 1
                    self._log(now, "OUT", vtype, vid)
                    self.last_event = {"direction": "OUT", "vehicle_type": vtype, "time": time.time()}

                self.history[vid] = y_center

                cv2.rectangle(frame, (x1, y1), (x2, y2), get_color_for_label(vtype), 2)
                cv2.putText(frame, f"{vtype} #{vid}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.55, get_color_for_label(vtype), 2)

        cv2.line(frame, (0, self.line_y), (w, self.line_y), (0, 0, 255), 3)
        cv2.putText(frame, f"IN: {self.count_in}  |  OUT: {self.count_out}", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 3)
        return frame

    def _log(self, ts, direction, vtype, vid):
        with open(self.log_path, "a", newline="") as f:
            csv.writer(f).writerow([ts, direction, vtype, vid, self.count_in, self.count_out])

    def get_recent_crossing(self, max_age_sec=6):
        """Vehicle type/direction of the most recent crossing, if recent enough
        to plausibly belong to the plate just read (used by Gate to correlate)."""
        if self.last_event and (time.time() - self.last_event["time"]) <= max_age_sec:
            return self.last_event
        return None

    def get_counts(self):
        return {"in": self.count_in, "out": self.count_out}
