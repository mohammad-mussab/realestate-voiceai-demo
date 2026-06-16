"""Tally form webhook -> outbound demo call.

When a lead submits the Tally form on the website, Tally POSTs the submission to
/webhooks/tally. We pull out the lead's name and phone number, then place an outbound
Twilio call to them. Twilio requests TwiML from /twiml/outbound, which connects the call's
media stream to our /ws endpoint (handled by pipecat's runner) so Ava can greet the lead.
"""

import os
import re
from urllib.parse import quote
from xml.sax.saxutils import escape

from loguru import logger

from pipecat.runner.run import app

from fastapi import Request
from fastapi.responses import Response

PHONE_RE = re.compile(r"[\d+]")
DEFAULT_BLOCKED_OUTBOUND_COUNTRY_CODES = ("+91", "+92", "+977", "+880")


def extract_lead_from_tally(payload: dict) -> dict:
    """Pull a lead's name and phone number out of a Tally form-response payload.

    Tally sends ``data.fields`` as a list of ``{key, label, type, value}`` dicts. Field
    keys/labels vary per form, so match defensively by type/label rather than fixed keys.

    Args:
        payload: Parsed JSON body of a Tally FORM_RESPONSE webhook.

    Returns:
        dict with "name" and "phone" (either may be None if not found). Phone is
        normalized to E.164, prefixing DEFAULT_COUNTRY_CODE if no "+" is present.
    """
    fields = (payload.get("data") or {}).get("fields") or []

    name = None
    phone = None

    for field in fields:
        label = (field.get("label") or "").lower()
        field_type = (field.get("type") or "").upper()
        value = field.get("value")

        if not value:
            continue

        if phone is None and (field_type in ("PHONE_NUMBER", "PHONE") or "phone" in label):
            phone = str(value)
        elif name is None and "name" in label:
            name = str(value)

    # Fallback: if no name found, use the first non-empty text field.
    if name is None:
        for field in fields:
            if (field.get("type") or "").upper() == "TEXT" and field.get("value"):
                name = str(field["value"])
                break

    if phone:
        phone = _normalize_phone(phone)

    if not phone:
        logger.warning(f"[tally] could not find a phone number in payload: {payload}")

    return {"name": name, "phone": phone}


def _normalize_phone(phone: str) -> str:
    """Strip formatting and add the default country code if missing."""
    digits = "".join(PHONE_RE.findall(phone))
    if digits.startswith("+"):
        return digits
    default_country_code = os.environ.get("DEFAULT_COUNTRY_CODE", "+1")
    return f"{default_country_code}{digits}"


def _blocked_outbound_country_codes() -> tuple[str, ...]:
    """Return country codes that should not receive outbound demo calls."""
    raw_codes = os.environ.get("BLOCKED_OUTBOUND_COUNTRY_CODES")
    if not raw_codes:
        return DEFAULT_BLOCKED_OUTBOUND_COUNTRY_CODES
    return tuple(code.strip() for code in raw_codes.split(",") if code.strip())


def is_outbound_phone_blocked(phone: str) -> bool:
    """Return True when the normalized phone starts with a blocked country code."""
    return phone.startswith(_blocked_outbound_country_codes())


async def trigger_outbound_call(name: str | None, phone: str) -> dict:
    """Place an outbound Twilio call to a lead, or log if Twilio isn't configured."""
    if is_outbound_phone_blocked(phone):
        logger.info(f"[outbound call - BLOCKED by country code] to={phone} name={name}")
        return {
            "called": False,
            "sid": None,
            "error": "Blocked country code",
            "blocked": True,
        }

    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_FROM_NUMBER")
    public_server_url = os.environ.get("PUBLIC_SERVER_URL")

    if not (account_sid and auth_token and from_number and public_server_url):
        logger.info(
            f"[outbound call - NOT PLACED, Twilio/PUBLIC_SERVER_URL not configured] "
            f"to={phone} name={name}"
        )
        return {"called": False, "sid": None, "error": "Twilio not configured"}

    try:
        from twilio.rest import Client

        client = Client(account_sid, auth_token)
        twiml_url = f"{public_server_url}/twiml/outbound?name={quote(name or 'there')}"
        call = client.calls.create(to=phone, from_=from_number, url=twiml_url, method="GET")
        logger.info(f"[outbound call placed] sid={call.sid} to={phone} name={name}")
        return {"called": True, "sid": call.sid, "error": None}
    except Exception as e:
        logger.error(f"[outbound call failed] to={phone}: {e}")
        return {"called": False, "sid": None, "error": str(e)}


@app.post("/webhooks/tally")
async def tally_webhook(request: Request):
    """Receive a Tally form submission and place an outbound demo call to the lead."""
    payload = await request.json()
    logger.debug(f"[tally] received payload: {payload}")

    lead = extract_lead_from_tally(payload)
    called = False
    blocked = False
    if lead["phone"]:
        result = await trigger_outbound_call(lead["name"], lead["phone"])
        called = result["called"]
        blocked = result.get("blocked", False)

    return {"received": True, "called": called, "blocked": blocked}


@app.get("/twiml/outbound")
@app.post("/twiml/outbound")
async def twiml_outbound(name: str = "there"):
    """Return TwiML that connects an outbound call's media stream to /ws."""
    public_server_url = os.environ.get("PUBLIC_SERVER_URL", "")
    ws_host = re.sub(r"^https?://", "", public_server_url)
    safe_name = escape(name)

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="wss://{ws_host}/ws">
      <Parameter name="call_type" value="outbound_demo"/>
      <Parameter name="lead_name" value="{safe_name}"/>
    </Stream>
  </Connect>
  <Pause length="40"/>
</Response>"""

    return Response(content=xml, media_type="application/xml")
