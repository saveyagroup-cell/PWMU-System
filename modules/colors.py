"""
Deterministic, visually-distinct color per class label — same idea as
Ultralytics' default results.plot() palette (jaisa detect_train.py chalane
par dikhta tha): har class ko apna consistent color milta hai, bina manually
har class ke liye color define kiye.
"""
import colorsys
import hashlib


def get_color_for_label(label: str):
    """Returns a consistent BGR tuple (for OpenCV) for any given class label."""
    h = int(hashlib.md5(label.encode()).hexdigest(), 16)
    hue = (h % 360) / 360.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.70, 0.95)
    return (int(b * 255), int(g * 255), int(r * 255))  # BGR order
