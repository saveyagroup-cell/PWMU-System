import os
import csv
import time
import threading
from datetime import datetime

import cv2
import numpy as np
import requests
from ultralytics import YOLO
import config
from modules import supabase_client

try:
    import torch
except Exception:
    torch = None


def _send_telegram_async(message, image_path=None):
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        return

    def _run():
        try:
            url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
            requests.post(url, data={"chat_id": config.TELEGRAM_CHAT_ID, "text": message}, timeout=5)
            if image_path and os.path.exists(image_path):
                photo_url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendPhoto"
                with open(image_path, "rb") as photo:
                    requests.post(photo_url, data={"chat_id": config.TELEGRAM_CHAT_ID},
                                  files={"photo": photo}, timeout=10)
        except Exception as e:
            print(f"[TELEGRAM] alert failed: {e}")

    threading.Thread(target=_run, daemon=True).start()


def _id_color(track_id):
    np.random.seed(int(track_id) * 35)
    c = np.random.randint(50, 255, size=3).tolist()
    return int(c[0]), int(c[1]), int(c[2])


class ThiefProcessor:
    def __init__(self):
        self.model = YOLO(config.THIEF_MODEL)
        self.track_history = {}
        self.entry_time = None
        self.last_alert_time = 0
        self.alarm_on = False
        self.zone_points = None  # set on first frame (center rectangle)
        self.recent_alerts = []
        self.log_path = os.path.join(config.CAPTURES_DIR, "thief_alerts_log.csv")
        self._ensure_log()
        self._warmup()

    def _warmup(self):
        """Absorb model-load/first-inference cost at startup, not on the
        first live frame — keeps the stream from stuttering at camera start."""
        dummy = np.zeros((config.INFER_IMGSZ, config.INFER_IMGSZ, 3), dtype=np.uint8)
        try:
            kwargs = dict(conf=config.THIEF_CONF, verbose=False, device=config.DEVICE,
                          half=config.USE_FP16, imgsz=config.INFER_IMGSZ)
            if torch is not None:
                with torch.inference_mode():
                    self.model.predict(dummy, **kwargs)
            else:
                self.model.predict(dummy, **kwargs)
            print("[THIEF] Model warm-up done.")
        except Exception as e:
            print(f"[THIEF] Warm-up skipped (non-fatal): {e}")

    def _ensure_log(self):
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w", newline="") as f:
                csv.writer(f).writerow(["Timestamp", "Reason", "TrackedIDs", "ImageURL"])

    def _default_zone(self, w, h):
        return [(int(w * 0.25), int(h * 0.2)), (int(w * 0.75), int(h * 0.2)),
                (int(w * 0.75), int(h * 0.85)), (int(w * 0.25), int(h * 0.85))]

    def process(self, frame):
        h, w = frame.shape[:2]
        if self.zone_points is None:
            self.zone_points = self._default_zone(w, h)
        pts = np.array(self.zone_points, np.int32).reshape((-1, 1, 2))

        track_kwargs = dict(persist=True, verbose=False, conf=config.THIEF_CONF,
                             device=config.DEVICE, half=config.USE_FP16, imgsz=config.INFER_IMGSZ)
        if torch is not None:
            with torch.inference_mode():
                results = self.model.track(frame, **track_kwargs)
        else:
            results = self.model.track(frame, **track_kwargs)

        person_in_zone = 0
        object_in_zone = False
        active_ids = []

        if results and results[0].boxes is not None and results[0].boxes.id is not None:
            for b in results[0].boxes:
                cls = int(b.cls[0])
                track_id = int(b.id[0]) if b.id is not None else -1
                xA, yA, xB, yB = map(int, b.xyxy[0])
                cx, cy = (xA + xB) // 2, (yA + yB) // 2
                inside = cv2.pointPolygonTest(pts, (float(cx), float(cy)), False) >= 0

                if cls == 0:  # person
                    color = _id_color(track_id)
                    self.track_history.setdefault(track_id, []).append((cx, cy))
                    self.track_history[track_id] = self.track_history[track_id][-20:]
                    for i in range(1, len(self.track_history[track_id])):
                        cv2.line(frame, self.track_history[track_id][i - 1],
                                  self.track_history[track_id][i], color, 2)
                    cv2.rectangle(frame, (xA, yA), (xB, yB), color, 2)
                    cv2.putText(frame, f"ID #{track_id}", (xA + 5, yA - 7),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                    if inside:
                        person_in_zone += 1
                        active_ids.append(track_id)
                        cv2.circle(frame, (cx, cy), 6, (0, 0, 255), -1)
                elif cls in config.BAG_CLASSES:
                    cv2.rectangle(frame, (xA, yA), (xB, yB), (0, 165, 255), 2)
                    cv2.putText(frame, "Bag/Object", (xA, yA - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)
                    if inside:
                        object_in_zone = True

        zone_color = (0, 0, 255) if person_in_zone > 0 else (0, 255, 0)
        cv2.polylines(frame, [pts], True, zone_color, 2)
        overlay = frame.copy()
        cv2.fillPoly(overlay, [pts], zone_color)
        cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)

        now_sec = time.time()
        now = datetime.now()
        is_night = True if config.TEST_MODE else (now.hour >= 22 or now.hour < 6)
        limit = config.LOITER_SECONDS_TEST if config.TEST_MODE else config.LOITER_SECONDS_NIGHT

        if is_night and person_in_zone > 0:
            if self.entry_time is None:
                self.entry_time = now_sec
            spent = int(now_sec - self.entry_time)
            cv2.putText(frame, f"Zone Timer: {spent}s / {limit}s", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            if spent >= limit or object_in_zone:
                reason = "UNATTENDED OBJECT!" if object_in_zone else "LOITERING THREAT!"
                cv2.putText(frame, f"ALERT: {reason}", (20, 80),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 3)
                if now_sec - self.last_alert_time > config.ALERT_COOLDOWN_SEC:
                    self._trigger_alert(frame, reason, active_ids, now)
                    self.last_alert_time = now_sec
        else:
            self.entry_time = None

        cv2.putText(frame, f"People: {person_in_zone} in zone", (20, h - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        return frame

    def _trigger_alert(self, frame, reason, active_ids, now):
        local_path = os.path.join(config.CAPTURES_DIR, f"alert_{int(now.timestamp())}.jpg")
        cv2.imwrite(local_path, frame)
        image_url = supabase_client.upload_image(local_path, "thief_alerts", bucket=config.SUPABASE_SECURITY_BUCKET)

        supabase_client.insert_row("thief_alerts", {
            "reason": reason,
            "tracked_ids": str(active_ids),
            "image_url": image_url,
            "detected_at": now.isoformat(),
        })

        with open(self.log_path, "a", newline="") as f:
            csv.writer(f).writerow([now.strftime("%Y-%m-%d %H:%M:%S"), reason, str(active_ids), image_url or ""])

        entry = {"reason": reason, "time": now.strftime("%H:%M:%S"), "url": image_url}
        self.recent_alerts.insert(0, entry)
        self.recent_alerts = self.recent_alerts[:15]

        msg = f"SECURITY ALERT\nReason: {reason}\nIDs: {active_ids}\nTime: {now.strftime('%Y-%m-%d %H:%M:%S')}"
        _send_telegram_async(msg, local_path)

    def get_recent(self):
        return self.recent_alerts
