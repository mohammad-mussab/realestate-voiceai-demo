"""Thin Twilio SMS helper. Falls back to logging if Twilio isn't configured."""

import os

from loguru import logger


def send_sms(to: str, body: str) -> dict:
    """Send an SMS via Twilio, or log it if Twilio credentials aren't set."""
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_FROM_NUMBER")

    if not (account_sid and auth_token and from_number):
        logger.info(f"[SMS - NOT SENT, Twilio not configured] to={to}: {body}")
        return {"sent": False, "sid": None, "error": "Twilio not configured"}

    try:
        from twilio.rest import Client

        client = Client(account_sid, auth_token)
        message = client.messages.create(body=body, from_=from_number, to=to)
        logger.info(f"[SMS sent] sid={message.sid} to={to}")
        return {"sent": True, "sid": message.sid, "error": None}
    except Exception as e:
        logger.error(f"[SMS failed] to={to}: {e}")
        return {"sent": False, "sid": None, "error": str(e)}
