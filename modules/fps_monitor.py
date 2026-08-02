"""Tiny reusable FPS counter — used by processors to overlay/log real-time
processing speed, and to help diagnose whether GPU/CPU inference is keeping
up with the camera."""
import time
import cv2


class FpsMonitor:
    def __init__(self, log_every_n_seconds=5):
        self._t0 = time.time()
        self._frames = 0
        self.fps = 0.0
        self._log_every = log_every_n_seconds
        self._last_log = time.time()

    def tick(self, label=""):
        self._frames += 1
        elapsed = time.time() - self._t0
        if elapsed >= 1.0:
            self.fps = self._frames / elapsed
            self._frames = 0
            self._t0 = time.time()
            if time.time() - self._last_log >= self._log_every:
                print(f"[FPS] {label}: {self.fps:.1f}")
                self._last_log = time.time()
        return self.fps

    def draw(self, frame, position="top-right"):
        h, w = frame.shape[:2]
        x = w - 110 if position == "top-right" else 15
        cv2.putText(frame, f"FPS: {self.fps:.1f}", (x, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
