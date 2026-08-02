"""
Smart Security (ESP32 IoT) Module
==================================
PIR + IR motion, flame, aur MQ-5 gas sensors — ESP32 board se USB serial ke
zariye data aata hai. Camera sirf sensor trigger par (ya DAY mode me
continuously) ON hoti hai, aur fire/gas/intrusion par PWMU ke existing
TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (config.py) se hi Telegram alert
jaata hai — koi alag credentials nahi chahiye.

Yeh standalone "SmartSecurity_Updated/flask_app.py" project ka logic hai,
jo yahan ek self-contained manager class me convert kiya gaya hai taaki
PWMU ke login/session, Gate & Security page, aur config ke saath seedha
integrate ho sake (alag Flask server chalane ki zaroorat nahi).

Note: is module me koi YOLO model NAHI chalta — sensor + plain camera feed
hi hai (halke weight, hamesha-ON ke liye). Agar future me person-detection
chahiye ho to yahi camera worker AI thief_detection ke saath extend ho
sakta hai.
"""
import os
import threading
import time
import queue
from datetime import datetime

import cv2
import requests

import config

try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


SS_CAPTURES_DIR = os.path.join(config.CAPTURES_DIR, "smart_security")
os.makedirs(SS_CAPTURES_DIR, exist_ok=True)


class SmartSecurityManager:
    """Ek hi instance poori app ke liye — ESP32 24x7 background me sunta
    rehta hai, chahe koi dashboard page khula ho ya nahi (isliye lazy-loaded
    processors ki tarah nahi, balki app start hote hi shuru hota hai)."""

    def __init__(self):
        self.sensor_data = {"pir": False, "ir": False, "fire": False, "gas": False, "gas_value": 0}
        self.esp32_status = {"state": "not_connected", "port": config.SS_SERIAL_PORT, "last_data_time": 0.0}
        self.camera_state = {"running": False, "reason": "standby"}
        self.mode_state = {
            "mode": config.SS_SECURITY_MODE,
            "night_start": config.SS_NIGHT_START,
            "night_end": config.SS_NIGHT_END,
        }

        self._serial_conn = None
        self._serial_lock = threading.Lock()
        self._stop_serial = threading.Event()

        self._frame_queue = queue.Queue(maxsize=1)
        self._cam_stop = threading.Event()
        self._cam_thread = None

        self._last_pir_time = 0.0
        self._last_ir_time = 0.0
        self._last_fire_time = 0.0
        self._last_intrusion_alert = 0.0
        self._last_fire_alert = 0.0
        self._last_gas_alert = 0.0
        self._buzzer_active = False
        self._recent_events = []   # in-memory alert log -> Gate & Security page table
        self._blank_cache = None
        self._started = False

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def start(self):
        if self._started:
            return
        self._started = True
        if SERIAL_AVAILABLE:
            threading.Thread(target=self._serial_reader_thread, daemon=True).start()
        else:
            print("[SMART-SECURITY] pyserial not installed -> ESP32 serial disabled (pip install pyserial).")
            self.esp32_status["state"] = "not_connected"
        threading.Thread(target=self._security_logic_thread, daemon=True).start()
        if self.mode_state["mode"] == "DAY":
            self._start_camera("day_mode")
        print(f"[SMART-SECURITY] Started (mode={self.mode_state['mode']}, port={config.SS_SERIAL_PORT})")

    # ------------------------------------------------------------------ #
    # Serial / ESP32 reader thread
    # ------------------------------------------------------------------ #
    def _parse_line(self, line):
        """'PIR:0,IR:0,FIRE:0,GAS:0,GAS_VALUE:123' -> self.sensor_data"""
        values = {}
        for item in line.split(","):
            if ":" not in item:
                continue
            key, val = item.split(":", 1)
            try:
                values[key.strip()] = int(val.strip())
            except ValueError:
                pass

        if values:
            self.sensor_data["pir"] = bool(values.get("PIR", 0))
            self.sensor_data["ir"] = bool(values.get("IR", 0))
            self.sensor_data["fire"] = bool(values.get("FIRE", 0))
            self.sensor_data["gas"] = bool(values.get("GAS", 0))
            self.sensor_data["gas_value"] = values.get("GAS_VALUE", 0)
            self.esp32_status["last_data_time"] = time.time()
            self.esp32_status["state"] = "connected"

    def _serial_reader_thread(self):
        port = config.SS_SERIAL_PORT
        while not self._stop_serial.is_set():
            if self._serial_conn is None or not self._serial_conn.is_open:
                self.esp32_status["state"] = "connecting"
                self.esp32_status["port"] = port
                try:
                    conn = serial.Serial(port, config.SS_BAUD_RATE, timeout=2)
                    with self._serial_lock:
                        self._serial_conn = conn
                    print(f"[SMART-SECURITY] ESP32 connected on {port}")
                    self.esp32_status["state"] = "connected"
                except Exception as e:
                    print(f"[SMART-SECURITY] ESP32 connect failed ({port}): {e}")
                    self.esp32_status["state"] = "not_connected"
                    self._stop_serial.wait(3)  # retry every 3s
                    continue

            try:
                raw = self._serial_conn.readline()
                line = raw.decode(errors="ignore").strip()
                if line:
                    self._parse_line(line)
            except Exception as e:
                print(f"[SMART-SECURITY] ESP32 read error: {e}")
                with self._serial_lock:
                    try:
                        if self._serial_conn:
                            self._serial_conn.close()
                    except Exception:
                        pass
                    self._serial_conn = None
                self.esp32_status["state"] = "not_connected"

        with self._serial_lock:
            if self._serial_conn and self._serial_conn.is_open:
                self._serial_conn.close()

    def _send_esp32(self, command):
        with self._serial_lock:
            if self._serial_conn and self._serial_conn.is_open:
                try:
                    self._serial_conn.write((command + "\n").encode())
                except Exception as e:
                    print(f"[SMART-SECURITY] ESP32 send error: {e}")

    # ------------------------------------------------------------------ #
    # Camera worker
    # ------------------------------------------------------------------ #
    def _cam_worker(self):
        cap = cv2.VideoCapture(config.SS_CAMERA_ID)
        if not cap.isOpened():
            print("[SMART-SECURITY] Cannot open camera")
            self.camera_state["running"] = False
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        print("[SMART-SECURITY] Camera started")

        while not self._cam_stop.is_set():
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue

            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            mode = self.mode_state["mode"]
            cv2.putText(frame, ts, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA)
            cv2.putText(frame, f"MODE: {mode}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 255), 1, cv2.LINE_AA)

            if self._frame_queue.full():
                try:
                    self._frame_queue.get_nowait()
                except queue.Empty:
                    pass
            try:
                self._frame_queue.put_nowait(frame)
            except queue.Full:
                pass

        cap.release()
        print("[SMART-SECURITY] Camera stopped")
        self.camera_state["running"] = False

    def _start_camera(self, reason="manual"):
        if self.camera_state["running"]:
            self.camera_state["reason"] = reason
            return
        self._cam_stop.clear()
        self.camera_state["running"] = True
        self.camera_state["reason"] = reason
        self._cam_thread = threading.Thread(target=self._cam_worker, daemon=True)
        self._cam_thread.start()

    def _stop_camera(self, reason="standby"):
        if not self.camera_state["running"]:
            self.camera_state["reason"] = reason
            return
        self._cam_stop.set()
        if self._cam_thread:
            self._cam_thread.join(timeout=3)
        self._cam_thread = None
        self.camera_state["running"] = False
        self.camera_state["reason"] = reason
        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                break

    # ------------------------------------------------------------------ #
    # Telegram (reuses config.TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)
    # ------------------------------------------------------------------ #
    def _telegram_configured(self):
        return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)

    def _send_telegram(self, message, image_path=None):
        if not self._telegram_configured():
            print("[SMART-SECURITY][TELEGRAM] not configured, skipping:", message)
            return
        try:
            if image_path and os.path.exists(image_path):
                url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendPhoto"
                with open(image_path, "rb") as photo:
                    requests.post(
                        url,
                        data={"chat_id": config.TELEGRAM_CHAT_ID, "caption": message},
                        files={"photo": photo},
                        timeout=10,
                    )
            else:
                url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
                requests.post(url, data={"chat_id": config.TELEGRAM_CHAT_ID, "text": message}, timeout=5)
        except Exception as e:
            print("[SMART-SECURITY][TELEGRAM ERROR]", e)

    def _trigger_alert(self, event_type, msg):
        def worker():
            frame = None
            for _ in range(15):
                if not self._frame_queue.empty():
                    frame = self._frame_queue.queue[-1]
                    break
                time.sleep(0.2)

            image_path = None
            image_url = None
            if frame is not None:
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                fname = f"{event_type}_{stamp}.jpg"
                image_path = os.path.join(SS_CAPTURES_DIR, fname)
                cv2.imwrite(image_path, frame)
                image_url = f"/captures/smart_security/{fname}"

            self._send_telegram(msg, image_path)

            now = datetime.now()
            self._recent_events.insert(0, {
                "reason": event_type,
                "msg": msg,
                "time": now.strftime("%H:%M:%S"),
                "date": now.strftime("%Y-%m-%d"),
                "url": image_url,
            })
            del self._recent_events[30:]

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------ #
    # Security decision loop
    # ------------------------------------------------------------------ #
    def _inside_time(self, start, end):
        current = datetime.now().strftime("%H:%M")
        if start <= end:
            return start <= current < end
        return current >= start or current < end

    def _security_logic_thread(self):
        while True:
            mode = self.mode_state["mode"].upper()
            pir = self.sensor_data["pir"]
            ir = self.sensor_data["ir"]
            fire = self.sensor_data["fire"]
            gas = self.sensor_data["gas"]
            now = time.time()

            if pir:
                self._last_pir_time = now
            if ir:
                self._last_ir_time = now
            if fire:
                self._last_fire_time = now

            recent_pir = (now - self._last_pir_time) <= config.SS_INTRUSION_WINDOW
            recent_ir = (now - self._last_ir_time) <= config.SS_INTRUSION_WINDOW
            recent_fire = (now - self._last_fire_time) <= config.SS_FIRE_WINDOW
            intrusion = recent_pir or recent_ir

            want_camera = False
            want_buzzer = False
            alert_reason = None
            alert_msg = None

            if mode == "DAY":
                # DAY: camera hamesha ON monitoring ke liye; buzzer sirf fire/gas par.
                want_camera = True
                if recent_fire:
                    want_buzzer = True
                    if now - self._last_fire_alert > config.SS_ALERT_COOLDOWN:
                        alert_reason, alert_msg = "fire", "🔥 FIRE ALERT!\nPWMU Shed — flame sensor triggered."
                        self._last_fire_alert = now
                elif gas:
                    want_buzzer = True
                    if now - self._last_gas_alert > config.SS_ALERT_COOLDOWN:
                        alert_reason = "gas"
                        alert_msg = f"⚠️ GAS LEAK ALERT!\nPWMU Shed — MQ-5: {self.sensor_data['gas_value']} PPM"
                        self._last_gas_alert = now
                elif intrusion:
                    if now - self._last_intrusion_alert > config.SS_ALERT_COOLDOWN:
                        alert_reason, alert_msg = "intrusion_day", "👀 DAY MONITORING\nMotion detected at PWMU Shed."
                        self._last_intrusion_alert = now

            else:
                # NIGHT / AUTO: camera sirf sensor-trigger par jaagti hai.
                is_night = mode == "NIGHT" or (
                    mode == "AUTO" and self._inside_time(self.mode_state["night_start"], self.mode_state["night_end"])
                )
                if recent_fire:
                    want_camera = True
                    want_buzzer = True
                    if now - self._last_fire_alert > config.SS_ALERT_COOLDOWN:
                        alert_reason, alert_msg = "fire", "🔥 FIRE ALERT!\nPWMU Shed — flame sensor triggered."
                        self._last_fire_alert = now
                elif gas:
                    want_camera = True
                    want_buzzer = True
                    if now - self._last_gas_alert > config.SS_ALERT_COOLDOWN:
                        alert_reason = "gas"
                        alert_msg = f"⚠️ GAS LEAK ALERT!\nPWMU Shed — MQ-5: {self.sensor_data['gas_value']} PPM"
                        self._last_gas_alert = now
                elif intrusion and is_night:
                    want_camera = True
                    want_buzzer = True
                    if now - self._last_intrusion_alert > config.SS_ALERT_COOLDOWN:
                        alert_reason, alert_msg = "intrusion_night", "🚨 INTRUSION ALERT (NIGHT)\nMotion detected at PWMU Shed!"
                        self._last_intrusion_alert = now
                elif intrusion:
                    # AUTO mode, din ke ghante — sirf camera dikhao, alert/buzzer nahi.
                    want_camera = True

            # Apply camera
            if want_camera and not self.camera_state["running"]:
                if self.camera_state["reason"] != "manual_stop":
                    reason = "day_mode" if mode == "DAY" else "sensor_trigger"
                    self._start_camera(reason)
            elif not want_camera and self.camera_state["running"] and self.camera_state["reason"] != "manual":
                self._stop_camera("standby")

            # Apply buzzer
            if want_buzzer and not self._buzzer_active:
                self._send_esp32("BUZZER_ON")
                self._buzzer_active = True
            elif not want_buzzer and self._buzzer_active:
                self._send_esp32("BUZZER_OFF")
                self._buzzer_active = False

            if alert_reason:
                self._trigger_alert(alert_reason, alert_msg)

            time.sleep(0.2)

    # ------------------------------------------------------------------ #
    # MJPEG stream
    # ------------------------------------------------------------------ #
    def gen_frames(self):
        while True:
            if not self.camera_state["running"]:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + self._blank_frame() + b"\r\n")
                time.sleep(0.4)
                continue
            try:
                frame = self._frame_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if not ok:
                continue
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n")

    def _blank_frame(self):
        if self._blank_cache is None:
            if NUMPY_AVAILABLE:
                img = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(img, "CAMERA STANDBY", (140, 220), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (180, 180, 180), 2)
                cv2.putText(img, "Waiting for sensor activation...", (90, 265), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (120, 120, 120), 1)
                _, buf = cv2.imencode(".jpg", img)
                self._blank_cache = buf.tobytes()
            else:
                self._blank_cache = b""
        return self._blank_cache

    # ------------------------------------------------------------------ #
    # Public API — used by Flask routes in app.py
    # ------------------------------------------------------------------ #
    def get_status(self):
        now = time.time()
        last_data = self.esp32_status.get("last_data_time", 0)
        conn_state = self.esp32_status["state"]
        if conn_state == "connected" and (now - last_data) > 5:
            conn_state = "not_connected"
            self.esp32_status["state"] = "not_connected"

        return {
            "esp32": {"state": conn_state, "port": self.esp32_status.get("port")},
            "sensors": dict(self.sensor_data),
            "camera": dict(self.camera_state),
            "buzzer": self._buzzer_active,
            "mode": self.mode_state["mode"],
            "night_start": self.mode_state["night_start"],
            "night_end": self.mode_state["night_end"],
            "time": datetime.now().strftime("%H:%M:%S"),
            "recent": self._recent_events[:20],
        }

    def set_mode(self, new_mode):
        new_mode = (new_mode or "DAY").upper()
        if new_mode not in ("DAY", "NIGHT", "AUTO"):
            return None
        self.mode_state["mode"] = new_mode
        print(f"[SMART-SECURITY] Mode switched to {new_mode}")

        if new_mode == "DAY":
            if not self.camera_state["running"] and self.camera_state["reason"] != "manual_stop":
                self._start_camera("day_mode")
        else:
            if self.camera_state["running"] and self.camera_state["reason"] != "manual":
                self._stop_camera("standby")
        return new_mode

    def buzzer(self, action):
        if action == "on":
            self._send_esp32("BUZZER_ON")
            self._buzzer_active = True
        elif action == "off":
            self._send_esp32("BUZZER_OFF")
            self._buzzer_active = False
        return self._buzzer_active

    def camera(self, action):
        if action == "start":
            self._start_camera("manual")
        elif action == "stop":
            self._stop_camera("manual_stop")
        return dict(self.camera_state)


# Single shared instance — app.py isko import karke .start() call karta hai.
smart_security = SmartSecurityManager()
