"""Post-call transcript analysis using Gemini.

Replaces mechanical tool-call accumulation: instead of only knowing what
capture_lead/qualify_lead/book_appointment happened to be called with before the
caller hung up, we ask Gemini to read the full transcript and extract the same
call_logs fields, so a call that got cut off mid-flow still yields a populated row.
"""

import json
import os
import time

from loguru import logger

MAX_RETRIES = 3
RETRY_BACKOFF_SECS = 2

CALL_LOGS_SCHEMA = {
    "type": "object",
    "properties": {
        "lead_name": {"type": "string"},
        "lead_phone": {"type": "string"},
        "lead_type": {"type": "string", "enum": ["buyer", "seller", "question"]},
        "timeline": {"type": "string"},
        "area": {"type": "string"},
        "price_range": {"type": "string"},
        "pre_approved": {"type": "boolean"},
        "property_needs": {"type": "string"},
        "seller_address": {"type": "string"},
        "appointment_type": {"type": "string", "enum": ["showing", "listing_consultation", "call_back"]},
        "appointment_time": {"type": "string"},
        "hot_lead": {"type": "boolean"},
        "notes": {"type": "string"},
    },
}

ANALYSIS_PROMPT = """You are analyzing a phone call transcript between Ava, a virtual \
assistant for Summit Realty Group (a real estate brokerage), and a caller. Extract the \
following details from the transcript as JSON matching the given schema. Leave a field \
out entirely if the transcript doesn't establish it (e.g. no appointment was booked, or \
the caller never gave a phone number) — do not invent or guess values.

- lead_name: caller's full name, only if they actually said it.
- lead_phone: caller's callback phone number, only if they actually said it.
- lead_type: "buyer", "seller", or "question".
- timeline: buyer/seller's stated timeline (e.g. "now", "1-3 months", "just browsing").
- area: city/neighborhood the caller mentioned.
- price_range: budget (buyer) or expected price range (seller), if mentioned.
- pre_approved: true only if a buyer explicitly said they're pre-approved for a mortgage.
- property_needs: beds/baths, house vs condo, or other stated requirements.
- seller_address: for sellers, the property address/area they want to sell.
- appointment_type: "showing", "listing_consultation", or "call_back" — only if one was \
actually agreed/booked in the call.
- appointment_time: the confirmed time window, only if an appointment was booked.
- hot_lead: true if the caller showed urgency (pre-approved + ready now, motivated \
seller with near-term deadline, or explicitly asked for an agent right away).
- notes: one short sentence of context useful for the agent following up (e.g. why no \
booking was made, what the caller specifically wants).

Transcript:
{transcript}
"""


def analyze_call(transcript: str) -> dict:
    """Run the call transcript through Gemini and return extracted call_logs fields.

    Returns an empty dict if GEMINI_API_KEY isn't set or the analysis call fails —
    callers should treat that as "no structured fields available" and still save the
    raw transcript.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.info("[call_analysis] GEMINI_API_KEY not set, skipping transcript analysis")
        return {}
    if not transcript.strip():
        return {}

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    model = os.environ.get("GEMINI_ANALYSIS_MODEL", "gemini-2.5-flash")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=ANALYSIS_PROMPT.format(transcript=transcript),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=CALL_LOGS_SCHEMA,
                    temperature=0,
                ),
            )
            fields = json.loads(response.text)
            logger.info(f"[call_analysis] extracted: {fields}")
            return fields
        except Exception as e:
            if attempt == MAX_RETRIES:
                logger.error(f"[call_analysis failed after {attempt} attempts] {e}")
                return {}
            logger.warning(f"[call_analysis] attempt {attempt} failed, retrying: {e}")
            time.sleep(RETRY_BACKOFF_SECS * attempt)

    return {}
