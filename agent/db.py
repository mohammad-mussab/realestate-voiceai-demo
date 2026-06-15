"""Thin Supabase helper for logging call summaries. Falls back to logging if unconfigured."""

import io
import os
import uuid
import wave

from loguru import logger

RECORDINGS_BUCKET = "call-recordings"


def audio_to_wav(audio: bytes, sample_rate: int, num_channels: int) -> bytes:
    """Wrap raw 16-bit PCM audio in a WAV container."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setsampwidth(2)
        wav_file.setnchannels(num_channels)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio)
    return buffer.getvalue()


def upload_recording(wav_bytes: bytes) -> dict:
    """Upload a call recording (WAV bytes) to Supabase Storage, or log if unconfigured.

    Returns a dict with "url" (signed URL, valid for 7 days) on success, or "error".
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not (url and key):
        logger.info(f"[recording - NOT SAVED, Supabase not configured] {len(wav_bytes)} bytes")
        return {"url": None, "error": "Supabase not configured"}

    try:
        from supabase import create_client

        client = create_client(url, key)
        path = f"{uuid.uuid4()}.wav"
        client.storage.from_(RECORDINGS_BUCKET).upload(
            path, wav_bytes, {"content-type": "audio/wav"}
        )
        signed = client.storage.from_(RECORDINGS_BUCKET).create_signed_url(path, 60 * 60 * 24 * 7)
        signed_url = signed.get("signedURL") or signed.get("signed_url")
        logger.info(f"[recording] saved: {path}")
        return {"url": signed_url, "error": None}
    except Exception as e:
        logger.error(f"[recording failed] {e}")
        return {"url": None, "error": str(e)}


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
