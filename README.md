## 0. What's new (latest update)

### Startup / "Start Camera" felt slow after adding ANPR + waste models
Fixed:
1. **Models now preload in the background the moment the server starts** (`app.py` warm-up thread) — YOLO models for Gate, both segregation stages, Shed, plus the EasyOCR reader. Previously this loading only happened the first time you clicked "Start Camera" for each module, making that first click take several seconds. Now it's paid once at server boot — cameras start instantly afterward. Watch the terminal for `[WARMUP] Done in Xs` to know when it's finished.
2. **Flask's debug auto-reloader is now off** (`use_reloader=False`) — it was silently running the whole app (including all model loading) **twice** in two separate processes, doubling both RAM usage and startup time. Trade-off: code changes now need a manual restart (`Ctrl+C` then `python app.py` again) instead of auto-reloading.
3. The Supabase storage-bucket reachability check at startup now also runs in the background instead of blocking server boot.


### Authentication (Supabase Auth)
Every page now requires sign-in. `/login` and `/signup` are the only public pages.
- Sign Up collects Name, PWM Unit, District, Email, Password → creates a Supabase Auth user + a row in the new `profiles` table.
- Sign In uses Supabase Auth (email/password). Session is a signed Flask cookie (`FLASK_SECRET_KEY`) — Supabase credentials never reach the browser.
- Profile dropdown (top-right) shows Name / PWM Unit / District + Sign Out.

### New navbar: Home / Gate & Security / AI Segregation / Dashboard
- **Home** (`/`) — overview cards only (icon + title + status chip). No subtitles, no "Open Module" text, no Project Highlights/USP section — all removed per spec.
- **Gate & Security** (`/gate-security`) — Vehicle Counter + ANPR + PWMU Shed Security, stacked on one page.
- **AI Segregation** (`/ai-segregation`) — Primary Segregation + Secondary Plastic Classification, stacked on one page.
- **Dashboard** (`/dashboard`) — the Analytics & Audit Report hub (4 charts + full PDF export), with proper "No records available" empty states instead of fake data.

The old per-module pages (`/module/...`), the 5-tab view (`/tabs`), and the original dark-theme pages (`/classic`) all still work as alternate deep-links.

### Real institutional logos
The NIT Raipur / Government of Chhattisgarh / UNICEF logos you provided are now actual image files in `static/images/` and used as `<img>` tags in the header (not text placeholders anymore).

### ANPR accuracy upgrade
`modules/plate.py` now uses **multi-frame, track-based OCR confirmation** (adapted from your high-accuracy standalone ANPR script):
- Each physical plate is tracked across frames (IOU matching) instead of reading a fresh crop every frame in isolation.
- A plate number is only "confirmed" once several independent frames agree (either 3 consecutive exact matches, or character-level weighted voting over more frames) — this stops one-off OCR mistakes (like 0/O) from being saved as fact.
- Shape filtering (aspect ratio + min area) rejects false positives like headlights/stickers.
- HSRP hologram noise ("IND" prefix/suffix) is cleaned up.
- Fuzzy duplicate detection (Levenshtein) stops the same plate being logged twice.
- **Not included:** the standalone script's own CSV/crops-folder system (`detected_plates.csv`, `unconfirmed_plates.csv`, separate folders) — this app already has its own CSV + Supabase save flow, so that part was intentionally left out to avoid two competing logging systems.

---

### Performance fix (video lag)
The old architecture ran camera-read + YOLO inference + JPEG-encode all inside the HTTP response loop — so the browser stream was only as fast as the slowest step, every single frame. Now:
- Each active module runs its own **background capture+inference thread**, fully decoupled from Flask's HTTP thread.
- A `queue.Queue(maxsize=1)` always holds only the **latest** frame — older, laggy frames are dropped, not queued up.
- Heavy inference (YOLO, and especially EasyOCR for plates) runs only every **Nth frame** (`config.FRAME_SKIP`, `config.PLATE_FRAME_SKIP`) — skipped frames reuse the last annotated overlay instead of re-running the model, so the stream stays smooth.
- JPEG quality is tunable via `config.JPEG_QUALITY` (default 75) for a further speed/quality trade-off.

### Vehicle Counter and ANPR are now fully separate modules
Previously combined into one "Gate" feed — now each has its own dedicated camera, page, and log, matching two independent camera setups (e.g. a wide gate camera for counting + a close-up camera for plates).

### New Executive Command Hub (home page `/`)
Card-based landing page — click a card to open that module's dedicated full page:
1. Vehicle Entry/Exit Counter
2. ANPR — Number Plate Records (with Search Plate + Manual Entry Override)
3. Primary Waste Segregation (Metal vs Other)
4. Secondary Plastic Classification (7 RIC types)
5. PWMU Shed Security (with browser audio alarm)
6. Analytics & Audit Report Hub — 4 charts (hourly intake/outflow, revenue by plastic type, composition doughnut, peak traffic hours) + full PDF export

The old 5-tab single-page view is still available at **`/tabs`**, and the original dark-theme pages at **`/classic`**.

### Mandatory institutional header + multi-language
Every page now shows a top strip with **NIT Raipur | Government of Chhattisgarh | UNICEF**, plus a language switcher (English / Hindi / Chhattisgarhi) covering the header and hub page text (`static/js/i18n.js`). To extend translations to more of the UI, add `data-i18n="your.key"` to any element and a matching entry in all three language blocks in `i18n.js`.

**Institutional logos:** the three circular badges (NR / CG / UN) in the header are text placeholders — official logo image files couldn't be generated or fetched here. Replace them in `templates/_header.html` with real `<img>` tags once you have the actual logo files from each institution.

### Supabase image uploads — hardened
If plate/theft images weren't showing up in Supabase, the most common causes are now handled:
- Startup now prints whether the storage bucket is actually reachable (check your terminal on boot).
- `supabase_schema.sql` now includes the **Storage RLS policies** needed for uploads to actually succeed (a "public" bucket only allows public *reads* by default — inserts still need an explicit policy, or the `service_role` key). Re-run the storage policy section of `supabase_schema.sql` if you haven't already.
- Recommended: use the **service_role** key (Project Settings → API) in `.env`, not `anon` — it bypasses Storage RLS entirely and is safe here since it's only used server-side in Flask, never sent to the browser.

---



| Module | Kya karta hai | Model |
|---|---|---|
| **Gate 1 (ANPR + Vehicle Count)** | Combined: line-crossing IN/OUT counter + plate detection/OCR on one feed | `yolov8s.pt` (auto-download) + `number_plate.pt` |
| **Conveyor 1 (Primary Segregation)** | Metal vs Other waste classification | `waste_primary.pt` (optional, new) |
| **Conveyor 2 (Secondary Plastic Classification)** | Plastic material + RIC type detect karta hai | `final_7types.pt` |
| **PWMU Shed (Thief/Loitering Detection)** | Zone-based loitering + unattended-object alert, Telegram + Supabase | `yolov8s.pt` (auto-download) |

Har module: **camera ON/OFF toggle**, live webcam ya **video upload** dono support karta hai.

---

## 1. Apni `.pt` files kahan daalein

Project ke `models/` folder me — **exactly yeh naam** rakhna zaroori hai (ya `config.py` me path change kar dena):

```
pwmu_dashboard/
└── models/
    ├── final_7types.pt          <- tumhara plastic 7-type model (detect_train.py wala)
    ├── waste_type_model.pt      <- OPTIONAL: dusra waste model agar hai (na ho to skip, app apne aap ek model se chalega)
    └── number_plate.pt          <- tumhara number plate model (number_plate2.py wala)
```

`yolov8s.pt` (vehicle count + thief detection ke liye) khud download nahi karna — Ultralytics pehli baar chalne par apne aap download kar lega. Agar offline chalana hai to isse bhi `models/` me daal ke `config.py` me path update kar dena.

---

## 2. Install & Setup

```bash
cd pwmu_dashboard
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

`.env.example` ko copy karke `.env` banao aur values bharo:

```bash
copy .env.example .env
```

Fill karo:
- `SUPABASE_URL`, `SUPABASE_KEY` — Supabase project settings se
- `SUPABASE_BUCKET` — default `pwmu-captures` rakh sakte ho
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — optional, thief alerts ke liye

> ⚠️ **Security note:** `boat5.py` me jo Telegram bot token/chat ID hardcoded tha, wo public/shared ho chuka hai maan ke chalo. BotFather me `/revoke` karke naya token banao aur sirf `.env` me daalo — code me kabhi hardcode mat karna.

---

## 3. Supabase setup

1. Supabase Dashboard → **SQL Editor** → `supabase_schema.sql` ka pura content paste karke run karo. Isse banega:
   - `plate_detections` table
   - `thief_alerts` table
   - `waste_sessions` table (optional future use)
   - `pwmu-captures` storage bucket (public)
2. Agar bucket auto-create na ho paye, manually: **Storage → New Bucket → name `pwmu-captures` → Public: ON**

App bina Supabase config ke bhi chalta hai (local-only mode) — bas cloud save/URL nahi milenge, sirf local `captures/` folder me images save hoti rahengi.

---

## 4. Run karo

```bash
python app.py
```

Browser me kholo: **http://localhost:5000**

- **Overview** page se sabhi 4 modules dikhte hain
- Har module page par **Start Camera** button se webcam chalu hoga (default index 0, `.env` me `CAMERA_INDEX` se change kar sakte ho)
- **Process Video** se koi bhi video file upload karke usi model se process kar sakte ho
- Waste + Vehicle modules me **Reset Counts** button bhi hai

---

## 5. Folder structure

```
pwmu_dashboard/
├── app.py                  # Flask app, routes, camera streaming
├── config.py                # Saari settings ek jagah
├── requirements.txt
├── .env.example
├── supabase_schema.sql
├── modules/
│   ├── waste.py             # Waste segregation processor (used by legacy /waste and Conveyor 2)
│   ├── waste_primary.py     # NEW: Conveyor 1 — Metal vs Other (optional model)
│   ├── gate.py              # NEW: Gate 1 — combines vehicle.py + plate.py on one feed
│   ├── vehicle.py           # Vehicle IN/OUT counter
│   ├── plate.py              # Number plate + OCR + Supabase save
│   ├── thief.py               # Loitering/theft detection + alerts
│   └── supabase_client.py    # Supabase upload/insert helper
├── templates/                # HTML pages (dark control-room UI)
├── static/css/style.css
├── static/js/main.js
├── models/                   # <-- apni .pt files yahan daalo
├── uploads/                  # uploaded videos yahan save hote hain
└── captures/                 # CSV logs + local image backups
```

---

## 6. Config tuning (`config.py`)

- `WASTE_CONF`, `VEHICLE_CONF`, `PLATE_CONF`, `THIEF_CONF` — confidence thresholds
- `VEHICLE_LINE_Y_RATIO` — IN/OUT line ki height (0.6 = frame ke 60% par)
- `TEST_MODE = True` — thief module jaldi trigger karega testing ke liye (5 sec). Real deployment ke liye `False` karo — tab sirf raat 10PM–6AM active hoga aur 5 min loitering par alert dega
- `FRAME_SKIP` — har Nth frame par hi inference (default 2) — CPU load kam karne ke liye, GPU ho to 1 rakh sakte ho

---

## 7. Aage kya add kar sakte ho

- Thief detection ka zone abhi frame ke center me fixed rectangle hai — agar chaho to canvas-drawing UI add karke user se 4-point polygon draw karwa sakte ho (jaisa `boat5.py` original me tha)
- Vehicle module me multiple counting lines / multi-camera support
- Role-based login (Admin/Operator) Supabase Auth se
- Waste module me daily/weekly composition chart (jaisa PWMU dashboard mockup me hai) — `waste_sessions` table already schema me hai isi ke liye
