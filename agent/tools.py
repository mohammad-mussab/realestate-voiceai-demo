"""Mocked tool functions for the Summit Realty Group voice agent demo.

All tools except send_confirmation_sms are mocked: they log a clearly-formatted
block and return a fake confirmation. send_confirmation_sms sends a real Twilio
SMS (or logs if Twilio isn't configured).
"""

import random

from loguru import logger

from sms import send_sms

from pipecat.services.llm_service import FunctionCallParams


async def check_area(params: FunctionCallParams, area: str):
    """Check whether Summit Realty Group serves the lead's city, neighborhood, or ZIP.

    Args:
        area: City, neighborhood, or ZIP code the lead mentioned.
    """
    out_of_area_terms = ("ottawa", "montreal", "vancouver", "calgary", "edmonton")
    covered = not any(term in area.lower() for term in out_of_area_terms)
    logger.info(f"[check_area] area={area} -> covered={covered}")
    await params.result_callback({"covered": covered, "area": area})


async def check_availability(params: FunctionCallParams, appointment_type: str, preferred_date: str = ""):
    """Get available appointment slots before offering or booking any appointment time.

    Args:
        appointment_type: One of "showing", "listing_consultation", or "call_back".
        preferred_date: ISO date or natural language like "this week".
    """
    if appointment_type == "listing_consultation":
        windows = ["tomorrow morning (9am-11am)", "tomorrow afternoon (1pm-3pm)", "Thursday morning (9am-11am)"]
    elif appointment_type == "call_back":
        windows = ["within the hour", "later this afternoon", "first thing tomorrow morning"]
    else:
        windows = ["today after 4pm", "tomorrow morning (10am-12pm)", "tomorrow afternoon (2pm-4pm)"]

    logger.info(f"[check_availability] appointment_type={appointment_type} preferred_date={preferred_date} -> {windows}")
    await params.result_callback({"available_windows": windows})


async def book_appointment(
    params: FunctionCallParams,
    name: str,
    phone: str,
    appointment_type: str,
    appointment_time: str,
    notes: str = "",
):
    """Book only after the chosen appointment_time was returned by check_availability.

    Args:
        name: Lead's full name.
        phone: Best callback phone number.
        appointment_type: One of "showing", "listing_consultation", or "call_back".
        appointment_time: Confirmed date and time window.
        notes: Short context for the agent (e.g. property of interest, address to sell).
    """
    booking_id = f"SRG-{random.randint(1000, 9999)}"
    logger.info(
        "APPOINTMENT BOOKED\n"
        f"  id: {booking_id}\n"
        f"  name: {name}\n"
        f"  phone: {phone}\n"
        f"  appointment_type: {appointment_type}\n"
        f"  time: {appointment_time}\n"
        f"  notes: {notes}"
    )
    await params.result_callback(
        {
            "booking_id": booking_id,
            "confirmed": True,
            "name": name,
            "appointment_type": appointment_type,
            "appointment_time": appointment_time,
        }
    )


async def alert_agent(
    params: FunctionCallParams,
    name: str,
    phone: str,
    reason: str,
    area: str = "",
):
    """Mandatory for hot leads once real name and phone are known.

    Hot leads include pre-approved urgent buyers, buyers who may move quickly,
    sellers who need to sell fast, and sellers relocating on a near-term deadline.

    Args:
        name: Lead's full name.
        phone: Best callback phone number.
        reason: Why this is hot (e.g. pre-approved and ready now, motivated seller).
        area: City, neighborhood, or property address relevant to the lead.
    """
    ticket_id = f"SRG-LEAD-{random.randint(1000, 9999)}"
    logger.info(
        "HOT LEAD ALERT\n"
        f"  ticket: {ticket_id}\n"
        f"  name: {name}\n"
        f"  phone: {phone}\n"
        f"  area: {area}\n"
        f"  reason: {reason}\n"
        "  agent notified, callback ETA: 10 minutes"
    )
    await params.result_callback(
        {
            "ticket_id": ticket_id,
            "alerted": True,
            "callback_eta_minutes": 10,
        }
    )


async def capture_lead(
    params: FunctionCallParams,
    phone: str = "",
    name: str = "",
    lead_type: str = "question",
    reason: str = "",
):
    """Save lead details as soon as real name and phone are known. Call once per call.

    Args:
        phone: Best callback phone number, if known yet.
        name: Lead's full name, if known.
        lead_type: One of "buyer", "seller", or "question".
        reason: Why a full booking wasn't made, if applicable.
    """
    if not name and not phone:
        logger.warning(f"capture_lead ignored empty contact details; lead_type={lead_type} reason={reason}")
        await params.result_callback(
            {
                "captured": False,
                "error": "name or phone is required before capture_lead",
            }
        )
        return

    logger.info(f"LEAD CAPTURED\n  name: {name}\n  phone: {phone}\n  lead_type: {lead_type}\n  reason: {reason}")
    await params.result_callback({"captured": True})


async def qualify_lead(
    params: FunctionCallParams,
    timeline: str,
    area: str = "",
    price_range: str = "",
    pre_approved: bool = False,
    property_needs: str = "",
    seller_address: str = "",
):
    """Record buyer/seller qualifying details once known; do not wait for booking.

    Args:
        timeline: e.g. "now", "1-3 months", or "just browsing".
        area: City or neighborhood of interest.
        price_range: Buyer's budget or seller's expected price range.
        pre_approved: True if a buyer has mortgage pre-approval.
        property_needs: Beds/baths, house vs condo, or other property requirements.
        seller_address: For sellers, the property they want to sell.
    """
    logger.info(
        "LEAD QUALIFIED\n"
        f"  timeline: {timeline}\n"
        f"  area: {area}\n"
        f"  price_range: {price_range}\n"
        f"  pre_approved: {pre_approved}\n"
        f"  property_needs: {property_needs}\n"
        f"  seller_address: {seller_address}"
    )
    await params.result_callback({"recorded": True})


async def transfer_to_human(params: FunctionCallParams, reason: str):
    """Transfer the caller to a human team member.

    Args:
        reason: Why the caller needs a human (e.g. frustrated, confused, off-topic request).
    """
    logger.info(f"TRANSFER REQUESTED\n  reason: {reason}")
    await params.result_callback(
        {
            "transferred": False,
            "message": "Our team will call you right back in a few minutes.",
        }
    )


async def send_confirmation_sms(params: FunctionCallParams, phone: str, message: str):
    """Send an SMS confirmation of the appointment to the lead.

    Args:
        phone: The lead's phone number, in E.164 format if possible (e.g. +14165551234).
        message: The confirmation text to send.
    """
    result = send_sms(to=phone, body=message)
    await params.result_callback(result)
