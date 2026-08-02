"""
PWMU Unified AI Control-Room Dashboard - Config
Sabhi model paths, thresholds aur Supabase settings yahan se control hote hain.
Environment variables .env file se load hote hain (python-dotenv).
"""
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
CAPTURES_DIR = os.path.join(BASE_DIR, "captures")

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(CAPTURES_DIR, exist_ok=True)

# ---------------- FLASK / SESSION ----------------
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-this-in-production")

# ---------------- DEVICE (GPU/CPU AUTO-DETECT) ----------------
# CUDA agar available hai to use karo, warna CPU pe gracefully fallback.
# FP16 (half precision) sirf CUDA par hi enable hota hai — CPU par half=True
# se error/slowdown hota hai isliye automatically off rehta hai.
try:
    import torch
    DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"
    USE_FP16 = torch.cuda.is_available()
except Exception:
    DEVICE = "cpu"
    USE_FP16 = False
print(f"[CONFIG] Inference device: {DEVICE} (FP16: {USE_FP16})")

# CPU par GPU jaisi raw speed kabhi nahi milegi (hardware limit hai, code se
# fix nahi hota) — lekin yeh settings CPU par jo speed possible hai wo milti
# hai: chhota inference resolution + chhota pretrained model + zyada frame-skip.
if DEVICE == "cpu":
    INFER_IMGSZ = int(os.environ.get("INFER_IMGSZ", 480))
    _COCO_PRETRAINED_MODEL = "yolov8n.pt"   # nano — GPU wale "small" se kaafi tez CPU par
else:
    INFER_IMGSZ = int(os.environ.get("INFER_IMGSZ", 640))
    _COCO_PRETRAINED_MODEL = "yolov8s.pt"

# ---------------- MODEL PATHS ----------------
# Apni trained .pt files "models/" folder me copy karo, exactly inn naamon se
# (README.md me pura detail hai)
#
# Conveyor 1 (Primary Segregation) aur Conveyor 2 (Secondary Plastic
# Classification) ab do POORI TARAH ALAG, standalone detectors hain — koi
# cascade/crop-into-each-other logic nahi hai. Har ek apna model, apna
# camera feed, apne boxes/labels khud draw karta hai. (Pehle waste_seg2.pt
# aur final_7types.pt ek dusre me "mix" ho rahe the — ab fix hai.)
WASTE_PRIMARY_MODEL = os.path.join(MODELS_DIR, "waste_seg2.pt")          # Conveyor 1: standalone
WASTE_MATERIAL_MODEL = os.path.join(MODELS_DIR, "final_7types.pt")       # Conveyor 2: standalone
WASTE_TYPE_MODEL_PATH = os.path.join(MODELS_DIR, "final_7types.pt")  # (legacy, optional 2nd model within old waste page)
PLATE_MODEL = os.path.join(MODELS_DIR, "number_plate.pt")               # Number plate detector
VEHICLE_MODEL = _COCO_PRETRAINED_MODEL   # COCO pretrained -> ultralytics auto-download; nano on CPU, small on GPU
THIEF_MODEL = _COCO_PRETRAINED_MODEL     # Same pretrained model, person + bag classes use hote hain

# ---------------- DETECTION SETTINGS ----------------
WASTE_CONF = 0.35          # Slightly lower threshold = better recall on real-world waste footage
WASTE_PRIMARY_CONF = 0.35
VEHICLE_CONF = 0.30
PLATE_CONF = 0.35
THIEF_CONF = 0.40

# ---- Secondary Plastic (Conveyor 2) — tuned separately ----
# imgsz=640: Increased resolution for maximum object detection and clarity
WASTE_SECONDARY_IMGSZ = int(os.environ.get("WASTE_SECONDARY_IMGSZ", 640))
# Lowered confidence threshold to detect more items
WASTE_SECONDARY_CONF  = float(os.environ.get("WASTE_SECONDARY_CONF",  0.20))
WASTE_SECONDARY_IOU   = float(os.environ.get("WASTE_SECONDARY_IOU",   0.45))
# ByteTrack: assigns a persistent track_id to each plastic item so the
# same bottle/bag isn't counted twice across frames.
WASTE_SECONDARY_USE_TRACK = os.environ.get("WASTE_SECONDARY_USE_TRACK", "1") != "0"
# Test-time augmentation: improves detection at multiple scales in one
# pass — turned ON for best accuracy
WASTE_SECONDARY_AUGMENT = os.environ.get("WASTE_SECONDARY_AUGMENT", "1") == "1"
# agnostic_nms=True: prevents two different plastic types being assigned to
# the same bounding box region (e.g. PET + HDPE on the same bottle).
WASTE_SECONDARY_AGNOSTIC_NMS = True
# Minimum detection box area in pixels (w*h) — lowered to 100 to detect smaller far away items
WASTE_SECONDARY_MIN_BOX_AREA = int(os.environ.get("WASTE_SECONDARY_MIN_BOX_AREA", 100))
# Optional ROI crop: restrict detection to a sub-region of the frame
# (saves compute + reduces false positives from non-belt background).
# Format: (x1_frac, y1_frac, x2_frac, y2_frac) as 0.0-1.0 fractions of frame size.
# Set to None to use the full frame (default).
# Example for conveyor belt in lower-centre: (0.05, 0.15, 0.95, 0.90)
WASTE_SECONDARY_ROI = None  # e.g. (0.05, 0.15, 0.95, 0.90)

VEHICLE_CLASSES = [1, 2, 3, 5, 7]  # bicycle, car, motorbike, bus, truck (COCO ids) — saare vehicle types
BAG_CLASSES = [24, 26, 28]         # backpack, handbag, suitcase (COCO ids)

VEHICLE_LINE_Y_RATIO = 0.6         # frame height ka 60% par IN/OUT line

# Loitering / thief detection
LOITER_SECONDS_TEST = 5            # test mode me jaldi trigger
LOITER_SECONDS_NIGHT = 300         # real mode me 5 min
ALERT_COOLDOWN_SEC = 12
TEST_MODE = True                   # False karo real deployment ke liye (raat 10pm-6am hi active hoga)

# OCR filters
PLATE_MIN_LEN = 4
PLATE_MIN_OCR_CONF = 0.40
PLATE_SAVE_COOLDOWN = 2.0
# OCR image size cap — 200px is sufficient for plate text and ~4x faster
# than 400px (EasyOCR time scales quadratically with image area).
PLATE_OCR_MAX_DIM = int(os.environ.get("PLATE_OCR_MAX_DIM", 200))
# Single-variant OCR: pick ONE preprocessing variant per crop based on
# brightness instead of always running 2–3 OCR passes. Cuts OCR calls ~60%.
PLATE_OCR_SINGLE_VARIANT = os.environ.get("PLATE_OCR_SINGLE_VARIANT", "1") != "0"

# ---- Advanced ANPR: multi-frame tracking + OCR voting (accuracy upgrade) ----
# Shape filter — rejects false positives like headlights/stickers
PLATE_MIN_ASPECT_RATIO = 1.3
PLATE_MAX_ASPECT_RATIO = 6.5
PLATE_MIN_BOX_AREA = 80

# Tracking (IOU-based, no extra library needed)
PLATE_TRACK_TIMEOUT = 2.0        # track expires if not seen for this long (seconds)
PLATE_IOU_MATCH_THRESH = 0.3
PLATE_READING_TIMEOUT = 1.5      # show unconfirmed plate faster (was 3.0s)

# Multi-frame OCR voting/confirmation
# NOTE: 1 frame early confirm = plate shows as soon as OCR is confident.
# This trades a tiny bit of accuracy for dramatically better UX.
PLATE_MIN_VOTE_FRAMES_EARLY = 1    # 1 frame with high conf -> early confirm (was 2)
PLATE_EARLY_CONFIRM_MIN_CONF = 0.50
PLATE_MAX_VOTE_FRAMES = 4          # strict fallback after this many frames (was 6)
PLATE_MIN_VOTE_AGREEMENT = 0.7

# Duplicate-plate detection (fuzzy match against already-saved plates this session)
PLATE_SIMILARITY_THRESHOLD = 0.82

# ---------------- OUTPUT / RECORDING ----------------
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)

# ---------------- ESTIMATED PLASTIC RESALE PRICES (₹ per kg) ----------------
# Yeh APPROXIMATE market rates hain — asli revenue ke liye weighing scale integration
# chahiye hoga. Abhi count-based rough estimate ke liye (avg 25g/item assume kiya hai).
# Keys match the 7 RIC types from final_7types.pt (uppercase).
PLASTIC_PRICE_PER_KG = {
    "PET":   18,   # Type 1 — bottles, jars
    "HDPE":  22,   # Type 2 — jugs, pipes
    "PVC":    8,   # Type 3 — low recyclability
    "LDPE":  14,   # Type 4 — bags, films
    "PP":    20,   # Type 5 — containers, caps
    "PS":     6,   # Type 6 — low recyclability
    "OTHER":  5,   # Type 7 — mixed/unknown
    # Legacy aliases (in case old model uses these names)
    "POLYPROPYLENE": 20, "POLYSTYRENE": 6, "OTHERS": 5,
}
ASSUMED_AVG_ITEM_WEIGHT_KG = 0.025  # 25 grams/item, rough estimate

# Per-type metadata for UI rendering (recyclability, color, RIC code)
PLASTIC_RIC_INFO = {
    "PET":   {"ric": 1, "full": "PET — Polyethylene Terephthalate",     "recyclable": True,  "color": "#3B82F6"},
    "HDPE":  {"ric": 2, "full": "HDPE — High-Density Polyethylene",     "recyclable": True,  "color": "#10B981"},
    "PVC":   {"ric": 3, "full": "PVC — Polyvinyl Chloride",              "recyclable": False, "color": "#EF4444"},
    "LDPE":  {"ric": 4, "full": "LDPE — Low-Density Polyethylene",      "recyclable": True,  "color": "#F59E0B"},
    "PP":    {"ric": 5, "full": "PP — Polypropylene",                   "recyclable": True,  "color": "#8B5CF6"},
    "PS":    {"ric": 6, "full": "PS — Polystyrene",                     "recyclable": False, "color": "#EC4899"},
    "OTHER": {"ric": 7, "full": "Other — Mixed / Unclassified Plastics", "recyclable": False, "color": "#6B7280"},
}

# ---------------- CAMERA ----------------
CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", 0))

# ---------------- SUPABASE ----------------
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
# Auth (sign up / sign in) MUST use the anon key — this is what Supabase Auth expects.
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
# Storage/DB writes: service_role is recommended (bypasses Storage RLS), but
# falls back to SUPABASE_KEY / anon key if that's all you've set.
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_KEY = SUPABASE_SERVICE_ROLE_KEY or os.environ.get("SUPABASE_KEY", "") or SUPABASE_ANON_KEY
SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "pwmu-captures")
SUPABASE_ANPR_BUCKET = os.environ.get("SUPABASE_ANPR_BUCKET", "anpr-detections")
SUPABASE_SECURITY_BUCKET = os.environ.get("SUPABASE_SECURITY_BUCKET", "security-detections")

# ---------------- TELEGRAM (optional, thief alerts) ----------------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ---------------- SMART SECURITY (ESP32: PIR + IR + Flame + MQ-5 Gas) ----------------
# Naya IoT section — ESP32 board se serial (USB) par sensor data aata hai,
# camera sirf sensor trigger par (ya DAY mode me continuously) ON hoti hai,
# aur fire/gas/intrusion par upar wale TELEGRAM_* credentials se hi alert jaata hai.
SS_SERIAL_PORT   = os.environ.get("SS_SERIAL_PORT", "COM14")   # ESP32 CH340 port — apne system ke hisaab se badlo
SS_BAUD_RATE     = int(os.environ.get("SS_BAUD_RATE", 115200))
SS_SECURITY_MODE = os.environ.get("SS_SECURITY_MODE", "AUTO")  # "DAY" | "NIGHT" | "AUTO" — runtime par /api/smart_security/set_mode se bhi badal sakte ho
SS_NIGHT_START   = os.environ.get("SS_NIGHT_START", "22:00")
SS_NIGHT_END     = os.environ.get("SS_NIGHT_END", "06:00")
SS_CAMERA_ID     = int(os.environ.get("SS_CAMERA_ID", CAMERA_INDEX))  # default: same webcam index as baaki modules
SS_INTRUSION_WINDOW = 5     # seconds: PIR/IR trigger ke baad itni der tak "recent" mana jaata hai
SS_FIRE_WINDOW      = 10    # seconds: flame sensor ka "active" window
SS_ALERT_COOLDOWN   = 60    # seconds: ek event-type ka 1 Telegram alert per minute

# Processing performance: har Nth frame par hi inference chalao (webcam ko smooth rakhne ke liye)
# CPU par zyada skip default rakha hai — GPU jitni speed CPU par possible nahi
# hai, isliye kam frequently inference chalana hi asli smooth-stream ka tareeka hai.
# Frame skip: run YOLO inference every Nth frame. Lower = more detections, higher CPU load.
# 3 on CPU gives ~2x inference attempts per second at 30fps camera — good balance.
_DEFAULT_FRAME_SKIP = 3 if DEVICE == "cpu" else 2
_DEFAULT_PLATE_FRAME_SKIP = 3 if DEVICE == "cpu" else 2
FRAME_SKIP = int(os.environ.get("FRAME_SKIP", _DEFAULT_FRAME_SKIP))
# Plate module sabse heavy hai (YOLO + EasyOCR dono) — isko zyada aggressively skip karo
PLATE_FRAME_SKIP = int(os.environ.get("PLATE_FRAME_SKIP", _DEFAULT_PLATE_FRAME_SKIP))
JPEG_QUALITY = int(os.environ.get("JPEG_QUALITY", 75))
print(f"[CONFIG] imgsz={INFER_IMGSZ}, FRAME_SKIP={FRAME_SKIP}, PLATE_FRAME_SKIP={PLATE_FRAME_SKIP}, "
      f"vehicle/thief model={_COCO_PRETRAINED_MODEL}")
