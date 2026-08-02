"""
Report generator — reads the per-module CSV logs (already being written by every
processor) and produces a filtered, downloadable CSV for Today / This Week /
This Month / All Time. No database needed — the CSVs in captures/ are the
source of truth, so this works even without Supabase configured.
"""
import csv
import io
import os
from datetime import datetime, timedelta

import config

LOG_FILES = {
    "gate": os.path.join(config.CAPTURES_DIR, "vehicle_log.csv"),
    "vehicle": os.path.join(config.CAPTURES_DIR, "vehicle_log.csv"),  # alias — Vehicle Counter is its own dedicated module now
    "plate": os.path.join(config.CAPTURES_DIR, "detected_plates.csv"),
    "waste_primary": os.path.join(config.CAPTURES_DIR, "waste_primary_log.csv"),
    "waste_secondary": os.path.join(config.CAPTURES_DIR, "waste_secondary_log.csv"),
    "thief": os.path.join(config.CAPTURES_DIR, "thief_alerts_log.csv"),
}

# Which column in each CSV holds the date (used for period filtering)
DATE_COLUMNS = {
    "gate": "Timestamp",
    "vehicle": "Timestamp",
    "plate": None,  # combines Date + Time columns, handled specially
    "waste_primary": "Timestamp",
    "waste_secondary": "Timestamp",
    "thief": "Timestamp",
}


def _period_start(period: str):
    now = datetime.now()
    if period == "daily":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "weekly":
        start = now - timedelta(days=now.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "monthly":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return None  # "all"


def _row_datetime(module, row):
    try:
        if module == "plate":
            return datetime.strptime(f"{row['Date']} {row['Time']}", "%Y-%m-%d %H:%M:%S")
        col = DATE_COLUMNS[module]
        return datetime.strptime(row[col], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def read_filtered(module: str, period: str = "all"):
    """Returns list of dict rows for one module, filtered by period."""
    path = LOG_FILES.get(module)
    if not path or not os.path.exists(path):
        return []

    start = _period_start(period)
    rows = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            ts = _row_datetime(module, row)
            if start is None or (ts and ts >= start):
                rows.append(row)
    return rows


def build_csv_response(module: str, period: str = "all"):
    """Returns (filename, csv_text) for a single module report."""
    rows = read_filtered(module, period)
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    else:
        buf.write("No records found for this period\n")
    filename = f"{module}_report_{period}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return filename, buf.getvalue()


def build_full_report_csv(period: str = "all"):
    """Merges all module logs into one CSV with a leading Module column."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Module", "Details (raw log row as JSON-ish)"])
    for module in LOG_FILES:
        rows = read_filtered(module, period)
        for row in rows:
            writer.writerow([module, str(row)])
    filename = f"pwmu_full_report_{period}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return filename, buf.getvalue()


def hourly_breakdown(module: str, period: str = "daily"):
    """Returns {hour(0-23): count} for bar-chart use — waste modules only."""
    rows = read_filtered(module, period)
    buckets = {h: 0 for h in range(24)}
    for row in rows:
        ts = _row_datetime(module, row)
        if ts:
            buckets[ts.hour] += 1
    return buckets
