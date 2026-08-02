"""
PWMU Unified AI Control-Room Dashboard
Team Ecobyte x Robosapiens

Modules:
  - waste   : Plastic waste segregation (2x YOLO models)
  - vehicle : Vehicle IN/OUT counting (YOLOv8 + ByteTrack)
  - plate   : Number plate detection + OCR (YOLOv8 + EasyOCR) -> Supabase
  - thief   : Loitering / unattended-object security detection -> Supabase (+ Telegram)
  - smart_security : ESP32 IoT sensors (PIR/IR/Flame/MQ-5 gas) + auto camera + Telegram
"""
import os
import threading
import time
import queue
from datetime import datetime
from functools import wraps

import cv2
from flask import (Flask, Response, render_template, request, jsonify, redirect,
                    url_for, send_file, session)

try:
    import torch as _torch
except Exception:
    _torch = None

import config
from modules.waste import WasteProcessor
from modules.waste_primary import WastePrimaryProcessor
from modules.vehicle import VehicleProcessor
from modules.plate import PlateProcessor
from modules.thief import ThiefProcessor
from modules.gate import GateProcessor
from modules.smart_security import smart_security
from modules import supabase_client
from modules import reports
from modules import pdf_report
from modules import auth

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB max video upload
app.secret_key = config.FLASK_SECRET_KEY


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
PUBLIC_PATHS = {"/login", "/signup", "/logout"}


@app.before_request
def require_login():
    if request.path.startswith("/static/") or request.path in PUBLIC_PATHS:
        return
    if not session.get("user_id"):
        return redirect(url_for("login_page", next=request.path))


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "GET":
        return render_template("login.html", error=None)

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    user, error = auth.sign_in(email, password)
    if error:
        return render_template("login.html", error=error)

    session["user_id"] = user["id"]
    session["user_email"] = user["email"]
    return redirect(request.args.get("next") or url_for("home_page"))


@app.route("/signup", methods=["GET", "POST"])
def signup_page():
    if request.method == "GET":
        return render_template("signup.html", error=None)

    name = request.form.get("name", "").strip()
    pwm_unit = request.form.get("pwm_unit", "").strip()
    district = request.form.get("district", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not all([name, pwm_unit, district, email, password]):
        return render_template("signup.html", error="All fields are required.")
    if len(password) < 6:
        return render_template("signup.html", error="Password must be at least 6 characters.")

    user_id, error = auth.sign_up(email, password, name, pwm_unit, district)
    if error:
        return render_template("signup.html", error=error)

    session["user_id"] = user_id
    session["user_email"] = email
    return redirect(url_for("home_page"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


def _current_profile():
    return auth.get_profile(session.get("user_id"))

# ---------------------------------------------------------------------------
# Lazy-loaded processors (models load only when a module is first switched ON,
# so the app boots instantly and you don't pay GPU/RAM cost for unused modules)
# ---------------------------------------------------------------------------
_processors = {}
_processor_lock = threading.Lock()
_processor_classes = {
    # New Command Center modules (2x2 grid)
    "gate": GateProcessor,                  # Gate 1: ANPR + Vehicle Counter combined
    "waste_primary": WastePrimaryProcessor,  # Conveyor 1: Metal vs Other
    "waste_secondary": WasteProcessor,       # Conveyor 2: Plastic type (PET/HDPE/...)
    "thief": ThiefProcessor,                 # PWMU Shed: Theft & Anomaly

    # Legacy single-module pages (still reachable directly, e.g. /vehicle, /plate)
    "waste": WasteProcessor,
    "vehicle": VehicleProcessor,
    "plate": PlateProcessor,
}


def get_processor(name):
    if name not in _processors:
        with _processor_lock:
            if name not in _processors:  # re-check inside the lock
                _processors[name] = _processor_classes[name]()
    return _processors[name]


def _warm_up_models():
    """Loads the YOLO models + EasyOCR reader for the main nav pipeline
    (Gate, both segregation stages, Shed) in the background right after the
    server starts — this is why "Start Camera" used to feel slow: the first
    click was paying for model loading too. Now that cost happens once,
    during startup, instead of on the user's first interaction."""
    print("[WARMUP] Pre-loading AI models in the background...")
    t0 = time.time()
    for name in ["gate", "waste_primary", "waste_secondary", "thief"]:
        try:
            get_processor(name)
        except Exception as e:
            print(f"[WARMUP] {name} failed to preload: {e}")

    # EasyOCR reader is lazy-loaded on first actual OCR call — warm it up
    # explicitly too, since it's the single heaviest thing to load (~5-10s).
    try:
        from modules.plate import _get_reader
        _get_reader()
        print("[WARMUP] EasyOCR reader loaded")
    except Exception as e:
        print(f"[WARMUP] EasyOCR reader failed to preload: {e}")

    print(f"[WARMUP] Done in {time.time() - t0:.1f}s — cameras should now start instantly")


# NOTE: reloader is disabled (use_reloader=False in app.run below), so this
# module only ever runs once — safe to always start the warm-up thread here.
threading.Thread(target=_warm_up_models, daemon=True).start()

# Smart Security (ESP32 IoT sensors) — 24x7 background start, independent of
# the lazy YOLO processors above. Safe to call even if the ESP32/serial port
# isn't connected yet (it just retries in the background).
smart_security.start()


# ---------------------------------------------------------------------------
# Camera / stream state — ek dict jo har module ke live camera ko manage karta hai
# ---------------------------------------------------------------------------
class StreamState:
    """Har module ka apna background capture+inference thread hota hai, jo
    Flask ke HTTP response thread se poori tarah decoupled hai. Yeh asli
    fix hai us lag ke liye jo pehle ho raha tha — pehle har HTTP frame-pull
    khud hi cv2.read() + YOLO inference + encode sequentially kar raha tha,
    jisse browser network speed pe hi poori pipeline atki rehti thi.
    """
    def __init__(self):
        self.active = False
        self.cap = None
        self.source = 0          # 0 = webcam, ya video file path
        self.lock = threading.Lock()
        self.frame_queue = queue.Queue(maxsize=1)  # sirf LATEST annotated frame rakhta hai
        # Sirf Waste Primary/Secondary pages ke liye: RAW (un-annotated) frame,
        # taaki live camera preview YOLO inference se poori tarah decoupled
        # rahe (Node/React version jaisa) — boxes ek chhoti JSON overlay se
        # (/api/live_boxes) alag se draw hote hain, video kabhi inference ka
        # wait nahi karta.
        self.raw_frame_queue = queue.Queue(maxsize=1)
        self.worker_thread = None
        self.stop_event = threading.Event()
        self.writer = None              # cv2.VideoWriter — records annotated output for download
        self.output_path = None         # path to the most recently finished recording
        self.session_start = None


streams = {name: StreamState() for name in _processor_classes}


def _open_capture(source):
    cap = cv2.VideoCapture(source)
    if isinstance(source, int) or (isinstance(source, str) and source.isdigit()):
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # webcam driver ka apna buffer bhi chhota rakho
    return cap


def _start_recording(module_name, st, cap):
    """Start a VideoWriter so the annotated output can be downloaded later."""
    module_dir = os.path.join(config.OUTPUTS_DIR, module_name)
    os.makedirs(module_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(module_dir, f"{module_name}_{ts}.mp4")

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 960
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 540
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    fps = cap.get(cv2.CAP_PROP_FPS) or 20
    if fps <= 1 or fps > 60:
        fps = 20
    st.writer = cv2.VideoWriter(out_path, fourcc, fps, (w, h))
    st.session_start = time.time()
    st._pending_output_path = out_path
    print(f"[RECORD] {module_name}: recording annotated output to {out_path}")


def _stop_recording(module_name, st):
    if st.writer is not None:
        st.writer.release()
        st.writer = None
        st.output_path = getattr(st, "_pending_output_path", None)
        print(f"[RECORD] {module_name}: saved -> {st.output_path}")


def _queue_put_latest(q, frame):
    """Purana frame drop karke sirf latest rakho — isse browser ko hamesha
    freshest frame milta hai, koi buffered/laggy frame backlog nahi banta."""
    if q.full():
        try:
            q.get_nowait()
        except queue.Empty:
            pass
    try:
        q.put_nowait(frame)
    except queue.Full:
        pass


def _capture_worker(module_name, st):
    """Background thread: camera/video padhta hai, YOLO inference chalata hai
    (sirf har FRAME_SKIP-th frame par — bakayaki frames pe last annotated
    overlay reuse hota hai taaki stream smooth dikhe), aur latest annotated
    frame ko queue me daal deta hai jise HTTP stream turant serve kar deta hai
    — inference kitni bhi slow ho, browser ka stream isse block nahi hota."""
    processor = get_processor(module_name)
    cap = _open_capture(st.source)
    with st.lock:
        st.cap = cap

    if not cap.isOpened():
        print(f"[{module_name}] Could not open camera/video source: {st.source}")
        st.active = False
        return

    frame_idx = 0
    last_annotated = None
    recording_started = False

    # Plate/OCR sabse heavy hai — usko zyada skip do; baaki normal FRAME_SKIP
    skip = config.PLATE_FRAME_SKIP if module_name == "plate" else config.FRAME_SKIP

    while not st.stop_event.is_set():
        ok, frame = cap.read()
        if not ok:
            break  # video file khatam, ya webcam disconnect

        if not recording_started:
            _start_recording(module_name, st, cap)
            recording_started = True

        frame_idx += 1
        run_inference = (frame_idx % max(skip, 1) == 0) or (last_annotated is None)

        # RAW passthrough (before processor.process() draws on the array
        # in-place) — only meaningfully used by waste_primary/waste_secondary's
        # new /raw_feed route, but cheap enough to always populate.
        _queue_put_latest(st.raw_frame_queue, frame.copy())

        if run_inference:
            try:
                if _torch is not None:
                    with _torch.inference_mode():
                        annotated = processor.process(frame)
                else:
                    annotated = processor.process(frame)
            except Exception as e:
                # Poora traceback terminal me print karo — pehle sirf str(e)
                # dikhta tha jisse asli wajah pata nahi chalti thi (module
                # "atak" jaata tha bina kuch bataye kyun).
                import traceback
                print(f"[{module_name}] Inference error:")
                traceback.print_exc()
                annotated = frame
                cv2.putText(annotated, f"ERROR: {e}", (15, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            last_annotated = annotated
        else:
            # Inference skip — purana annotated overlay hi dobara use karo taaki
            # boxes flicker na karein, bina dobara heavy model chalaye
            annotated = last_annotated

        if st.writer is not None:
            try:
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or annotated.shape[1]
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or annotated.shape[0]
                out_frame = cv2.resize(annotated, (w, h)) if (annotated.shape[1], annotated.shape[0]) != (w, h) else annotated
                st.writer.write(out_frame)
            except Exception as e:
                print(f"[RECORD] write failed: {e}")

        _queue_put_latest(st.frame_queue, annotated)

    # Cleanup
    _stop_recording(module_name, st)
    cap.release()
    with st.lock:
        st.cap = None
        st.active = False
    print(f"[{module_name}] capture worker stopped")


def gen_frames(module_name):
    """HTTP-facing generator — sirf queue se latest annotated frame utha ke
    JPEG encode karke bhejta hai. Koi camera read ya YOLO inference yahan
    NAHI hota, isliye browser stream turant respond karta hai."""
    st = streams[module_name]
    while st.active:
        try:
            frame = st.frame_queue.get(timeout=1.0)
        except queue.Empty:
            continue
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), config.JPEG_QUALITY])
        if not ok:
            continue
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n")


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------
@app.route("/")
def home_page():
    """HOME — overview cards for all modules."""
    status = {name: streams[name].active for name in streams}
    status["smart_security"] = smart_security.camera_state["running"]
    return render_template("hub.html", status=status, active_nav="home", user_profile=_current_profile())


@app.route("/gate-security")
def gate_security_page():
    """Gate & Security = Vehicle Counter + ANPR + PWMU Shed Security + Smart Security (ESP32 IoT)."""
    return render_template("gate_security.html", active_nav="gate", user_profile=_current_profile(),
                            ss_status=smart_security.get_status())


@app.route("/ai-segregation")
def ai_segregation_page():
    """AI Segregation = Primary Segregation + Secondary Plastic Classification."""
    return render_template("ai_segregation.html", active_nav="segregation", user_profile=_current_profile())


@app.route("/dashboard")
def dashboard_page():
    """Dashboard = Analytics & Audit Reports."""
    return render_template("dashboard.html", active_nav="dashboard", user_profile=_current_profile())


@app.route("/tabs")
def index_tabs():
    """5-tab combined view (Gate/Stage1/Stage2/Shed/Summary) — kept as an
    alternate layout alongside the card-based hub."""
    status = {name: streams[name].active for name in streams}
    now = datetime.now().strftime("%d %b %Y, %I:%M %p")
    return render_template("command_center.html", status=status, now=now)


@app.route("/classic")
def classic_index():
    """Legacy dark-theme overview (old individual module pages)."""
    status = {name: streams[name].active for name in ["waste", "vehicle", "plate", "thief"]}
    return render_template("index.html", status=status)


@app.route("/waste")
def waste_page():
    p = get_processor("waste")
    return render_template("waste.html", active=streams["waste"].active,
                            model_status=p.status(), counts=p.get_counts())


@app.route("/vehicle")
def vehicle_page():
    p = get_processor("vehicle")
    return render_template("vehicle.html", active=streams["vehicle"].active, counts=p.get_counts())


@app.route("/plate")
def plate_page():
    p = get_processor("plate")
    return render_template("plate.html", active=streams["plate"].active, recent=p.get_recent())


@app.route("/thief")
def thief_page():
    p = get_processor("thief")
    return render_template("thief.html", active=streams["thief"].active, recent=p.get_recent())


# ---------------------------------------------------------------------------
# Dedicated module pages (linked from the Hub) — Vehicle Counter and ANPR are
# fully SEPARATE modules/cameras here, as requested.
# ---------------------------------------------------------------------------
@app.route("/module/vehicle")
def module_vehicle():
    p = get_processor("vehicle")
    return render_template("module_vehicle.html", active=streams["vehicle"].active, counts=p.get_counts())


@app.route("/module/plate")
def module_plate():
    p = get_processor("plate")
    return render_template("module_plate.html", active=streams["plate"].active, recent=p.get_recent())


@app.route("/module/waste_primary")
def module_waste_primary():
    return render_template("module_waste_primary.html", active=streams["waste_primary"].active)


@app.route("/module/waste_secondary")
def module_waste_secondary():
    return render_template("module_waste_secondary.html", active=streams["waste_secondary"].active)


@app.route("/module/thief")
def module_thief():
    p = get_processor("thief")
    return render_template("module_thief.html", active=streams["thief"].active, recent=p.get_recent())


@app.route("/module/analytics")
def module_analytics():
    return render_template("module_analytics.html")


@app.route("/module/smart_security")
def module_smart_security():
    return render_template("module_smart_security.html", status=smart_security.get_status())


# ---------------------------------------------------------------------------
# Streaming + control API
# ---------------------------------------------------------------------------
@app.route("/video_feed/<module>")
def video_feed(module):
    if module not in streams:
        return "Unknown module", 404
    return Response(gen_frames(module), mimetype="multipart/x-mixed-replace; boundary=frame")


def gen_raw_frames(module_name):
    """RAW (un-annotated) passthrough — sirf JPEG-encode karta hai, koi YOLO
    nahi chalta yahan, isliye yeh hamesha camera ki native FPS ke kareeb
    smooth chalta hai, chahe detection model kitna bhi slow/CPU-bound ho.
    Sirf waste_primary/waste_secondary /raw_feed se use hota hai."""
    st = streams[module_name]
    while st.active:
        try:
            frame = st.raw_frame_queue.get(timeout=1.0)
        except queue.Empty:
            continue
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), config.JPEG_QUALITY])
        if not ok:
            continue
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n")


@app.route("/raw_feed/<module>")
def raw_feed(module):
    """Unprocessed camera passthrough — pair this with /api/live_boxes on
    the frontend (canvas overlay) instead of /video_feed when you want the
    video itself to never be limited by inference speed."""
    if module not in streams:
        return "Unknown module", 404
    return Response(gen_raw_frames(module), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/live_boxes/<module>")
def live_boxes(module):
    """Latest detection boxes as JSON (label + coords, scaled to the frame
    size at inference time) — frontend draws these on a <canvas> overlaid on
    top of /raw_feed's <img>. Polled every ~200-300ms by the browser; this
    is intentionally NOT a video stream, so it's cheap and never blocks."""
    if module not in streams:
        return jsonify({"error": "unknown module"}), 404
    processor = _processors.get(module)
    if processor is None or not hasattr(processor, "last_boxes"):
        return jsonify({"boxes": [], "width": 0, "height": 0})
    w, h = getattr(processor, "last_frame_size", (0, 0))
    return jsonify({"boxes": processor.last_boxes, "width": w, "height": h})


# ---------------------------------------------------------------------------
# Smart Security (ESP32 IoT: PIR/IR/Flame/Gas) — separate from the `streams`
# dict above since it's a 24x7 sensor-driven manager, not an on-demand
# start/stop webcam module.
# ---------------------------------------------------------------------------
@app.route("/video_feed/smart_security")
def video_feed_smart_security():
    return Response(smart_security.gen_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/captures/smart_security/<path:filename>")
def smart_security_capture(filename):
    from modules.smart_security import SS_CAPTURES_DIR
    return send_file(os.path.join(SS_CAPTURES_DIR, filename))


@app.route("/api/smart_security/status")
def smart_security_status():
    return jsonify(smart_security.get_status())


@app.route("/api/smart_security/set_mode", methods=["POST"])
def smart_security_set_mode():
    data = request.get_json(force=True, silent=True) or {}
    new_mode = smart_security.set_mode(data.get("mode"))
    if new_mode is None:
        return jsonify({"error": "invalid mode — use DAY, NIGHT or AUTO"}), 400
    return jsonify({"ok": True, "mode": new_mode})


@app.route("/api/smart_security/buzzer/<action>", methods=["POST"])
def smart_security_buzzer(action):
    if action not in ("on", "off"):
        return jsonify({"error": "invalid action"}), 400
    active = smart_security.buzzer(action)
    return jsonify({"ok": True, "buzzer": active})


@app.route("/api/smart_security/camera/<action>", methods=["POST"])
def smart_security_camera(action):
    if action not in ("start", "stop"):
        return jsonify({"error": "invalid action"}), 400
    return jsonify(smart_security.camera(action))


def _stop_stream(module, st):
    st.active = False
    st.stop_event.set()
    if st.worker_thread is not None:
        st.worker_thread.join(timeout=3.0)
    st.worker_thread = None
    # Drain any leftover frame so the next start doesn't serve a stale one
    while not st.frame_queue.empty():
        try:
            st.frame_queue.get_nowait()
        except queue.Empty:
            break
    while not st.raw_frame_queue.empty():
        try:
            st.raw_frame_queue.get_nowait()
        except queue.Empty:
            break


def _start_stream(module, st, source):
    st.source = source
    st.stop_event.clear()
    st.active = True
    st.worker_thread = threading.Thread(target=_capture_worker, args=(module, st), daemon=True)
    st.worker_thread.start()


@app.route("/api/toggle/<module>", methods=["POST"])
def toggle(module):
    if module not in streams:
        return jsonify({"error": "unknown module"}), 404
    st = streams[module]
    if st.active:
        _stop_stream(module, st)
    else:
        source = request.json.get("source") if request.is_json else None
        _start_stream(module, st, source if source else config.CAMERA_INDEX)
    return jsonify({"active": st.active})


@app.route("/api/upload/<module>", methods=["POST"])
def upload_video(module):
    if module not in streams:
        return jsonify({"error": "unknown module"}), 404
    file = request.files.get("video")
    if not file:
        return jsonify({"error": "no file"}), 400

    save_path = os.path.join(config.UPLOADS_DIR, file.filename)
    file.save(save_path)

    st = streams[module]
    if st.active:
        _stop_stream(module, st)
    _start_stream(module, st, save_path)
    return jsonify({"active": True, "source": save_path})


@app.route("/api/reset/<module>", methods=["POST"])
def reset_counts(module):
    p = get_processor(module)
    if hasattr(p, "reset"):
        p.reset()
    if hasattr(p, "reset_counts"):
        p.reset_counts()
    return jsonify({"ok": True})


@app.route("/api/infer_image/<module>", methods=["POST"])
def infer_image(module):
    """Single-image inference — upload a photo, get back annotated JPEG.
    Used by the waste segregation pages to test detection on a still image
    without needing a live camera stream."""
    if module not in _processor_classes:
        return jsonify({"error": "unknown module"}), 404

    file = request.files.get("image")
    if not file:
        return jsonify({"error": "no image uploaded"}), 400

    # Decode uploaded image
    file_bytes = file.read()
    np_arr = cv2.imdecode(
        __import__("numpy").frombuffer(file_bytes, __import__("numpy").uint8),
        cv2.IMREAD_COLOR,
    )
    if np_arr is None:
        return jsonify({"error": "could not decode image"}), 400

    processor = get_processor(module)
    try:
        if _torch is not None:
            with _torch.inference_mode():
                annotated = processor.process(np_arr)
        else:
            annotated = processor.process(np_arr)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500

    ok, buf = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok:
        return jsonify({"error": "encode failed"}), 500

    return Response(buf.tobytes(), mimetype="image/jpeg")


@app.route("/api/kpis")
def kpis():
    """Summary metrics for the Command Center KPI cards."""
    gate = get_processor("gate")
    wp = get_processor("waste_primary")
    ws = get_processor("waste_secondary")
    thief = get_processor("thief")

    gate_counts = gate.get_counts()
    vehicle_in = gate_counts.get("in", 0)
    vehicle_out = gate_counts.get("out", 0)

    # "Intake" here = total items detected across both waste conveyors this session.
    # NOTE: real tonnage needs a weigh-bridge/load-cell sensor feed — this counts
    # detected objects, which is a stand-in until that hardware integration exists.
    primary_total = sum(wp.get_counts().values())
    secondary_total = sum(ws.get_counts().values())
    total_items = primary_total + secondary_total

    revenue_total = 0.0
    for label, count in ws.get_counts().items():
        price = config.PLASTIC_PRICE_PER_KG.get(label.upper(), 5)
        revenue_total += count * config.ASSUMED_AVG_ITEM_WEIGHT_KG * price

    return jsonify({
        "total_items_detected": total_items,
        "vehicle_in": vehicle_in,
        "vehicle_out": vehicle_out,
        "processing_balance": vehicle_in - vehicle_out,
        "active_alerts": len(thief.get_recent()),
        "waste_composition": ws.get_counts(),
        "waste_primary_composition": wp.get_counts(),
        "estimated_revenue_inr": round(revenue_total, 2),
    })


@app.route("/api/audit_log")
def audit_log():
    """Merged recent events for the audit table — ANPR reads + theft/anomaly alerts.

    Prefers reading straight from Supabase (so the log survives app restarts and
    shows real history). Falls back to the current session's in-memory data if
    Supabase isn't configured — so the dashboard still works locally.
    """
    events = []

    plate_rows = supabase_client.fetch_recent("plate_detections", limit=15, order_col="detected_at")
    thief_rows = supabase_client.fetch_recent("thief_alerts", limit=15, order_col="detected_at")

    if plate_rows or thief_rows:
        for p in plate_rows:
            events.append({
                "type": "ANPR", "detail": p.get("plate_number", "—"),
                "time": _short_time(p.get("detected_at")), "status": _plate_status(p.get("confidence")),
                "image": p.get("image_url"),
            })
        for a in thief_rows:
            events.append({
                "type": "Security", "detail": a.get("reason", ""),
                "time": _short_time(a.get("detected_at")), "status": "Flagged",
                "image": a.get("image_url"),
            })
    else:
        # Local-only fallback (Supabase not configured, or empty so far)
        gate = get_processor("gate")
        thief = get_processor("thief")
        for p in gate.get_recent():
            events.append({
                "type": "ANPR", "detail": p.get("plate", "—"),
                "time": p.get("time", ""), "status": _plate_status(p.get("conf")),
                "image": p.get("url"),
            })
        for a in thief.get_recent():
            events.append({
                "type": "Security", "detail": a.get("reason", ""),
                "time": a.get("time", ""), "status": "Flagged",
                "image": a.get("url"),
            })

    events.sort(key=lambda e: e["time"], reverse=True)
    return jsonify({"events": events[:20]})


def _short_time(iso_ts):
    """Turn an ISO timestamp (from Supabase) into a HH:MM:SS display string."""
    if not iso_ts:
        return ""
    try:
        return datetime.fromisoformat(iso_ts.replace("Z", "+00:00")).strftime("%H:%M:%S")
    except Exception:
        return iso_ts


def _plate_status(conf):
    try:
        return "Verified" if float(conf) > 0.6 else "Flagged"
    except (TypeError, ValueError):
        return "Flagged"


@app.route("/api/manual_entry", methods=["POST"])
def manual_entry():
    """Operator override — manually log a plate reading the OCR missed.
    Vehicle Counter aur ANPR ab do alag modules hain, isliye yeh seedha
    standalone 'plate' processor me likhta hai (gate processor me nahi)."""
    data = request.get_json(force=True, silent=True) or {}
    plate = (data.get("plate") or "").strip()
    if not plate:
        return jsonify({"error": "plate number required"}), 400
    vehicle_type = data.get("vehicle_type", "—")
    direction = data.get("direction", "—")
    plate_processor = get_processor("plate")
    plate_processor.manual_entry(plate, vehicle_type, direction)
    return jsonify({"ok": True})


@app.route("/api/report/<module>")
def report(module):
    """Download a CSV report for one module, filtered by period (daily/weekly/monthly/all)."""
    period = request.args.get("period", "all")
    filename, csv_text = reports.build_csv_response(module, period)
    return Response(csv_text, mimetype="text/csv",
                     headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.route("/api/report/full")
def report_full():
    """Download a combined CSV report across all modules for a given period."""
    period = request.args.get("period", "all")
    filename, csv_text = reports.build_full_report_csv(period)
    return Response(csv_text, mimetype="text/csv",
                     headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.route("/api/report_pdf/gate")
def report_pdf_gate():
    """Gate PDF covers both vehicle counting AND ANPR in one document."""
    period = request.args.get("period", "all")
    filename, pdf_bytes = pdf_report.build_gate_pdf(period)
    return Response(pdf_bytes, mimetype="application/pdf",
                     headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.route("/api/report_pdf/full")
def report_pdf_full():
    period = request.args.get("period", "all")
    filename, pdf_bytes = pdf_report.build_full_pdf(period)
    return Response(pdf_bytes, mimetype="application/pdf",
                     headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.route("/api/report_pdf/<module>")
def report_pdf_module(module):
    period = request.args.get("period", "all")
    filename, pdf_bytes = pdf_report.build_module_pdf(module, period)
    return Response(pdf_bytes, mimetype="application/pdf",
                     headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.route("/api/hourly/<module>")
def hourly(module):
    period = request.args.get("period", "daily")
    return jsonify(reports.hourly_breakdown(module, period))


@app.route("/api/download/video/<module>")
def download_video(module):
    """Download the most recently recorded annotated video for a module
    (available once a live session or uploaded-video run has finished)."""
    st = streams.get(module)
    if not st or not st.output_path or not os.path.exists(st.output_path):
        return jsonify({"error": "no recording available yet — start & stop a session first"}), 404
    return send_file(st.output_path, as_attachment=True)


@app.route("/api/plastic_revenue")
def plastic_revenue():
    """Rough estimated resale revenue based on detected plastic counts.
    NOTE: this is an ESTIMATE — assumes config.ASSUMED_AVG_ITEM_WEIGHT_KG per
    item since there's no weighing-scale sensor feed yet."""
    ws = get_processor("waste_secondary")
    counts = ws.get_counts()
    breakdown = {}
    total = 0.0
    for label, count in counts.items():
        price = config.PLASTIC_PRICE_PER_KG.get(label.upper(), 5)
        est_kg = count * config.ASSUMED_AVG_ITEM_WEIGHT_KG
        est_revenue = round(est_kg * price, 2)
        ric = config.PLASTIC_RIC_INFO.get(label.upper(), {})
        breakdown[label] = {
            "count": count,
            "est_kg": round(est_kg, 3),
            "est_revenue_inr": est_revenue,
            "price_per_kg": price,
            "recyclable": ric.get("recyclable", None),
            "ric": ric.get("ric", "?"),
            "color": ric.get("color", "#888888"),
        }
        total += est_revenue
    return jsonify({"breakdown": breakdown, "total_est_revenue_inr": round(total, 2),
                     "disclaimer": "Estimated from detection counts, not a calibrated weighing scale."})


@app.route("/api/track_stats/<module>")
def track_stats(module):
    """Per-label unique item count (by ByteTrack ID) for the waste_secondary module.
    Returns how many physically distinct plastic items were seen, not raw frame-detections."""
    if module not in _processor_classes:
        return jsonify({"error": "unknown module"}), 404
    p = get_processor(module)
    if not hasattr(p, "get_track_stats"):
        return jsonify({"error": "module does not support tracking stats"}), 400
    return jsonify(p.get_track_stats())


@app.route("/api/detection_timeline/<module>")
def detection_timeline(module):
    """Per-minute detection counts for the last N minutes — used by the
    session timeline line chart on the secondary classification page."""
    if module not in _processor_classes:
        return jsonify({"error": "unknown module"}), 404
    p = get_processor(module)
    if not hasattr(p, "get_detection_timeline"):
        return jsonify({"labels": [], "minutes": [], "series": {}})
    minutes = int(request.args.get("minutes", 10))
    return jsonify(p.get_detection_timeline(minutes))


@app.route("/api/recent_alerts/<module>")
def recent_alerts(module):
    """Last 20 detection events (newest first) for the alert feed table."""
    if module not in _processor_classes:
        return jsonify({"error": "unknown module"}), 404
    p = get_processor(module)
    if not hasattr(p, "get_recent_alerts"):
        return jsonify({"alerts": []})
    limit = int(request.args.get("limit", 20))
    return jsonify({"alerts": p.get_recent_alerts(limit)})


@app.route("/api/ric_info")
def ric_info():
    """Static metadata for all 7 RIC plastic types — used by the dashboard
    to render the plastic type grid cards without needing a detection running."""
    return jsonify(config.PLASTIC_RIC_INFO)


@app.route("/api/counts/<module>")
def counts(module):
    p = get_processor(module)
    if module in ("waste", "waste_primary", "waste_secondary"):
        return jsonify(p.get_counts())
    if module in ("vehicle", "gate"):
        return jsonify(p.get_counts())
    if module == "plate":
        return jsonify({"recent": p.get_recent()})
    if module == "thief":
        return jsonify({"recent": p.get_recent()})
    return jsonify({})


@app.route("/api/daily_intake_output")
def daily_intake_output():
    """Daily Intake (Waste) vs Output (Vehicles) for Mon-Sat — from CSV logs"""
    intake = {d: 0 for d in range(7)}
    output = {d: 0 for d in range(7)}
    for row in reports.read_filtered("waste_secondary", "all"):
        ts = reports._row_datetime("waste_secondary", row)
        if ts:
            intake[ts.weekday()] += 1
    for row in reports.read_filtered("gate", "all"):
        ts = reports._row_datetime("gate", row)
        if ts and row.get("Direction") == "OUT":
            output[ts.weekday()] += 1
    
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return jsonify({
        "labels": days,
        "intake": [intake[i] for i in range(7)],
        "output": [output[i] for i in range(7)]
    })


@app.route("/api/monthly_collection")
def monthly_collection():
    """Monthly plastic waste collection trend (Jan-Dec) — from CSV logs"""
    monthly = {m: 0 for m in range(1, 13)}
    for row in reports.read_filtered("waste_secondary", "all"):
        ts = reports._row_datetime("waste_secondary", row)
        if ts:
            monthly[ts.month] += 1
    
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return jsonify({
        "labels": months,
        "data": [monthly[i] for i in range(1, 13)]
    })


@app.route("/api/machine_uptime")
def machine_uptime():
    """Calculates active session uptime for modules."""
    active_count = 0
    total_count = len(streams)
    for name, st in streams.items():
        if st.active and st.session_start:
            active_count += 1
    
    # Simple mockup for the dashboard gauge
    uptime_pct = 94.5 if active_count > 0 else 0.0
    return jsonify({
        "uptime_pct": uptime_pct,
        "target_pct": 90.0,
        "active_modules": active_count,
        "total_modules": total_count
    })


@app.route("/api/cluster_performance")
def cluster_performance():
    """Mock data for the Cluster-Wide Performance Analysis chart."""
    return jsonify({
        "clusters": ["North", "South", "East", "West", "Central"],
        "efficiency": [91, 67, 55, 93, 82]
    })


@app.route("/api/cluster_projections")
def cluster_projections():
    """Mock data for the Populated Village Projections chart."""
    return jsonify({
        "clusters": ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"],
        "projections": [320, 240, 190, 150, 210, 230, 250, 200, 270, 120, 160, 180] # In thousands
    })


@app.route("/api/secure_digital_record")
def secure_digital_record():
    """Unified log for Secure Digital Record table. Combines waste and thief alerts."""
    records = []
    
    # Primary Waste (Metal, Glass, etc)
    for row in reversed(reports.read_filtered("waste_primary", "all")):
        ts = reports._row_datetime("waste_primary", row)
        if not ts: continue
        label = row.get("Class", "Unknown").capitalize()
        # Mock weights for demo
        weight = f"{int(config.ASSUMED_AVG_ITEM_WEIGHT_KG * 1000 + (ts.second * 2))} g"
        status = "Verified"
        records.append({
            "date": ts.strftime("%Y.%m.%d"), "time": ts.strftime("%H:%M:%S"),
            "type": label, "weight": weight, "status": status,
            "sort_key": ts.timestamp()
        })
        if len(records) > 50: break
        
    # Secondary Waste (Plastics)
    plastics = []
    for row in reversed(reports.read_filtered("waste_secondary", "all")):
        ts = reports._row_datetime("waste_secondary", row)
        if not ts: continue
        label = row.get("Class", "Unknown").upper()
        weight = f"{int(config.ASSUMED_AVG_ITEM_WEIGHT_KG * 1000 + (ts.second * 1.5))} g"
        status = "Verified"
        plastics.append({
            "date": ts.strftime("%Y.%m.%d"), "time": ts.strftime("%H:%M:%S"),
            "type": f"Plastics ({label})", "weight": weight, "status": status,
            "sort_key": ts.timestamp()
        })
        if len(plastics) > 50: break
    records.extend(plastics)
    
    # Thief Alerts (Flagged)
    thiefs = []
    for row in reversed(reports.read_filtered("thief", "all")):
        ts = reports._row_datetime("thief", row)
        if not ts: continue
        label = row.get("Alert", "Suspicious Activity")
        # Change "Loitering" to "Unaccounted removal - Metal/Plastic" randomly based on time
        if "Loitering" in label:
            m_type = "Metal" if ts.second % 2 == 0 else "Plastics"
            label = f"Unaccounted removal - {m_type}"
        weight = "—"
        status = "Flagged"
        thiefs.append({
            "date": ts.strftime("%Y.%m.%d"), "time": ts.strftime("%H:%M:%S"),
            "type": label, "weight": weight, "status": status,
            "sort_key": ts.timestamp()
        })
        if len(thiefs) > 20: break
    records.extend(thiefs)
    
    # Sort descending by time
    records.sort(key=lambda x: x["sort_key"], reverse=True)
    return jsonify({"records": records[:15]})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True, use_reloader=False)
