"""
Supabase helper — image upload (Storage) + row insert (Database).
Agar SUPABASE_URL / SUPABASE_KEY set nahi hai to yeh silently skip ho jata hai
(local capture folder me image save hoti rahegi, app crash nahi karega).
"""
import os
import time
import threading
import traceback

import config

_client = None
_enabled = bool(config.SUPABASE_URL and config.SUPABASE_KEY)

if _enabled:
    try:
        from supabase import create_client
        _client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
        print(f"[SUPABASE] Connected to {config.SUPABASE_URL}")

        def _check_buckets_background():
            # Startup check: do the storage buckets actually exist & are reachable?
            # Runs in a background thread so slow/failed network calls to Supabase
            # don't add multiple seconds to every app startup (this was previously
            # blocking, synchronous — a real contributor to the "slow to load" feel).
            for bucket in {config.SUPABASE_BUCKET, config.SUPABASE_ANPR_BUCKET, config.SUPABASE_SECURITY_BUCKET}:
                try:
                    _client.storage.from_(bucket).list()
                    print(f"[SUPABASE] Storage bucket '{bucket}' reachable")
                except Exception as bucket_err:
                    print(f"[SUPABASE] WARNING: bucket '{bucket}' not reachable: {bucket_err}")
                    print(f"[SUPABASE]   -> Create it: Dashboard > Storage > New Bucket "
                          f"(name exactly '{bucket}', Public: ON), or run supabase_schema.sql")

        threading.Thread(target=_check_buckets_background, daemon=True).start()
    except Exception:
        print("[SUPABASE] Client init failed, running in local-only mode:")
        traceback.print_exc()
        _enabled = False


def is_enabled():
    return _enabled


def upload_image(local_path, remote_prefix, bucket=None):
    """Upload image to a Supabase Storage bucket. Returns public URL or None."""
    if not _enabled:
        return None
    bucket = bucket or config.SUPABASE_BUCKET
    filename = f"{remote_prefix}/{int(time.time()*1000)}_{os.path.basename(local_path)}"
    try:
        with open(local_path, "rb") as f:
            # file_options keys must be strings (supabase-py is picky about this
            # across versions) — this is a common silent-failure point.
            _client.storage.from_(bucket).upload(
                path=filename, file=f, file_options={"content-type": "image/jpeg"}
            )
        url = _client.storage.from_(bucket).get_public_url(filename)
        print(f"[SUPABASE] Uploaded -> {bucket}/{filename}")
        return url
    except Exception as e:
        print(f"[SUPABASE] Image upload FAILED for {bucket}/{filename}: {e}")
        traceback.print_exc()
        return None


def insert_row(table, row: dict):
    """Insert a row into a Supabase table. Fails silently (logs error) if not configured."""
    if not _enabled:
        return None
    try:
        return _client.table(table).insert(row).execute()
    except Exception:
        print(f"[SUPABASE] Insert into '{table}' failed:")
        traceback.print_exc()
        return None


def fetch_recent(table, limit=15, order_col="detected_at"):
    """Read back the most recent rows from a Supabase table (for the audit log).
    Returns [] if Supabase isn't configured or the query fails — caller should
    fall back to in-memory data in that case."""
    if not _enabled:
        return []
    try:
        res = (
            _client.table(table)
            .select("*")
            .order(order_col, desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception:
        print(f"[SUPABASE] fetch_recent from '{table}' failed:")
        traceback.print_exc()
        return []
