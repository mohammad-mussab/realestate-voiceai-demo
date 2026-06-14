"""Thin Supabase helper for logging call summaries. Falls back to logging if unconfigured."""

import os

from loguru import logger


def log_call(summary: dict) -> dict:
    """Insert a call summary row into Supabase, or log it if Supabase isn't configured."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not (url and key):
        logger.info(f"[call_logs - NOT SAVED, Supabase not configured] {summary}")
        return {"saved": False, "error": "Supabase not configured"}

    try:
        from supabase import create_client

        client = create_client(url, key)
        client.table("call_logs").insert(summary).execute()
        logger.info(f"[call_logs] saved: {summary}")
        return {"saved": True, "error": None}
    except Exception as e:
        logger.error(f"[call_logs failed] {summary}: {e}")
        return {"saved": False, "error": str(e)}
