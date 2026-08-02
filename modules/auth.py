"""
Authentication — uses Supabase Auth for email/password sign up & sign in,
and stores extra profile fields (name, pwm_unit, district) in a `profiles`
table. Runs entirely server-side (Flask), so the service-role/anon keys
never reach the browser.
"""
import traceback

import config

_auth_client = None
_enabled = bool(config.SUPABASE_URL and (config.SUPABASE_ANON_KEY or config.SUPABASE_KEY))

if _enabled:
    try:
        from supabase import create_client
        # Auth flows should use the anon key (Supabase Auth's intended client type).
        _auth_client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY or config.SUPABASE_KEY)
    except Exception:
        print("[AUTH] Could not init Supabase auth client:")
        traceback.print_exc()
        _enabled = False


def is_enabled():
    return _enabled


def sign_up(email, password, name, pwm_unit, district):
    """Returns (user_id, error_message). error_message is None on success."""
    if not _enabled:
        return None, "Authentication is not configured (SUPABASE_URL / SUPABASE_ANON_KEY missing)."
    try:
        res = _auth_client.auth.sign_up({"email": email, "password": password})
        if not res.user:
            return None, "Sign up failed — no user returned."
        user_id = res.user.id

        # Save profile fields separately (Supabase Auth only stores email/password)
        from modules import supabase_client
        supabase_client.insert_row("profiles", {
            "id": user_id, "name": name, "pwm_unit": pwm_unit,
            "district": district, "email": email,
        })
        return user_id, None
    except Exception as e:
        msg = str(e)
        print(f"[AUTH] sign_up failed: {msg}")
        return None, msg


def sign_in(email, password):
    """Returns (user_dict, error_message). user_dict has id/email on success."""
    if not _enabled:
        return None, "Authentication is not configured (SUPABASE_URL / SUPABASE_ANON_KEY missing)."
    try:
        res = _auth_client.auth.sign_in_with_password({"email": email, "password": password})
        if not res.user:
            return None, "Invalid email or password."
        return {"id": res.user.id, "email": res.user.email}, None
    except Exception as e:
        msg = str(e)
        # Supabase returns fairly technical messages — normalize the common one
        if "Invalid login credentials" in msg:
            msg = "Invalid email or password."
        print(f"[AUTH] sign_in failed: {msg}")
        return None, msg


def get_profile(user_id):
    """Fetch profile fields (name/pwm_unit/district) for header display."""
    if not _enabled or not user_id:
        return None
    try:
        from modules import supabase_client
        if not supabase_client.is_enabled():
            return None
        res = supabase_client._client.table("profiles").select("*").eq("id", user_id).limit(1).execute()
        rows = res.data or []
        return rows[0] if rows else None
    except Exception:
        traceback.print_exc()
        return None
