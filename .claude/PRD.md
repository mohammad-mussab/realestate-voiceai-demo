# Product Requirements Document (PRD)

## Overview

**Feature Name**: Summit Realty Group Voice Agent Demo + Outbound Call Request Form

**Summary**: A browser/phone voice agent ("Ava") for a fictional real estate brokerage
("Summit Realty Group"), plus a lead-capture web form that triggers an outbound demo call from
Ava via Twilio + Pipecat Cloud.

**Goal**: Give prospective real estate business customers a tangible, "wow" demo: they enter
their name and phone number, Ava calls them within moments, qualifies them as a buyer or
seller, detects hot leads, and books a showing or listing consultation (or escalates a hot
lead). The experience should convince the prospect that this agent could run their phone line.

---

## Current State (built)

- `agent/bot.py` — Pipecat pipeline: WebRTC transport -> `LLMContextAggregatorPair` ->
  `GeminiLiveLLMService` (`gemini-3.1-flash-live-preview`, voice-to-voice) -> transport output.
  Runs locally via `python bot.py`, browser client at `http://localhost:7860/client`. A
  `CallSummaryObserver` captures lead/qualification/booking data from tool calls and logs a
  call summary to Supabase (`agent/db.py`) on disconnect.
- `agent/prompts.py` — `SYSTEM_INSTRUCTION` defining Ava's persona, buyer/seller qualifying
  flow, hot-lead detection, info-capture flow, booking flow, and hard rules (fair housing, no
  valuations, no legal/tax/mortgage advice, etc.).
- `agent/tools.py` — `check_area`, `check_availability`, `book_appointment`, `alert_agent`,
  `capture_lead`, `qualify_lead`, `transfer_to_human` (all mocked — log + fake confirmation),
  and `send_confirmation_sms` (real Twilio send via `agent/sms.py`, falls back to logging if
  Twilio env vars unset).
- `agent/db.py` — `log_call()`, real Supabase insert into `call_logs`, falls back to logging
  if Supabase env vars unset.
- `agent/tests/` — scripted scenario tests (`run_scenarios.py` + `scenarios.json`) driving Ava
  through text conversations against the real Gemini Live API, with an LLM judge grading
  pass/fail.

---

## User Stories

### Primary User (demo prospect / real estate brokerage owner)
- As a prospect, I want to enter my name and phone number on a simple web form, so that Ava
  calls me and I can experience the agent firsthand without dialing in myself.
- As a prospect, I want the call to feel like a real brokerage intake call (qualifying,
  hot-lead detection, booking, SMS confirmation), so I can judge whether this would work for
  my business.

### Secondary User (demo operator — us)
- As the demo operator, I want to deploy Ava on Pipecat Cloud so it can make/receive real
  phone calls via Twilio, not just browser WebRTC.
- As the demo operator, I want the outbound call to be triggered reliably from the form
  submission with minimal latency, so the prospect doesn't wait long after submitting.

---

## Requirements

### Functional Requirements
1. Web form: collects name + phone number (E.164 or normalizable format), submits to a backend
   endpoint.
2. Backend: on form submission, initiates an outbound call via Twilio to the submitted phone
   number, connecting the call to the Pipecat Cloud-hosted Ava agent.
3. Ava (Pipecat Cloud deployment): same persona/behavior as the local demo
   (`SYSTEM_INSTRUCTION` in `agent/prompts.py`), but running on a telephony transport
   (Twilio <-> Pipecat Cloud) instead of WebRTC.
4. Existing tool behavior (qualifying, hot-lead alerting, booking, SMS confirmation, Supabase
   call logging) carries over unchanged to the phone-call deployment.

### Non-Functional Requirements
- **Performance**: Outbound call should connect within seconds of form submission — latency is
  part of the "wow" factor.
- **Language**: English.
- **Integration**: Twilio (outbound calling + SMS), Pipecat Cloud (agent hosting), Gemini Live
  API (voice-to-voice LLM), Supabase (call log storage).

---

## Open Questions

> These need answers before the outbound-call feature can be planned/implemented in detail —
> do not assume, ask the user.

- Where does the web form live (separate frontend app, static page, part of this repo)? What
  stack (plain HTML, React, etc.)?
- What triggers the outbound call — a backend server endpoint we build, or Twilio Studio/Flow,
  or a Pipecat Cloud "dial-out" API?
- Do we have a Pipecat Cloud account/project set up yet, or is that still to be created?
- Do we have a Twilio phone number provisioned for outbound calls (separate from/same as the
  SMS `TWILIO_FROM_NUMBER`)?
- Any rate-limiting / abuse protection needed on the form (since it triggers real outbound
  calls and costs)?

---

## Acceptance Criteria

### Must Have
- [ ] Local browser demo continues to work unchanged (`agent/bot.py` + `/client`)
- [ ] Ava deployed to Pipecat Cloud, reachable via Twilio
- [ ] Web form collects name + phone, triggers an outbound call to that number
- [ ] Outbound call connects to Ava with the same persona/tools as the local demo
- [ ] SMS confirmation still works on the phone-call path (if Twilio configured)

### Nice to Have
- [ ] Form submissions logged/stored for follow-up
- [ ] Basic abuse protection (rate limit, phone number validation)

---

## Testing Plan

### Test Scenarios
1. **Happy Path**: Submit form with valid number -> receive call -> routine buyer/seller
   qualifying + booking flow completes -> SMS confirmation received.
2. **Hot Lead Path**: During the outbound call, signal urgency/pre-approval/near-term timeline
   -> Ava correctly detects a hot lead and calls `alert_agent`.
3. **Edge Case**: Invalid/unreachable phone number submitted via form -> graceful failure, no
   crash.

### Test Commands
```bash
cd agent
source .venv/bin/activate
python tests/run_scenarios.py                 # all scenarios (text-based, local)
python tests/run_scenarios.py --scenario hot_lead_preapproved_buyer
```

chat_test.py (text-only local test, no voice) — `python chat_test.py`, open `localhost:7861`.

---

## Technical Notes

### Files likely involved (outbound-call feature, not yet planned in detail)
- `agent/bot.py` — may need a telephony transport variant for Pipecat Cloud/Twilio
- New: web form (location TBD per open questions)
- New: backend endpoint to trigger outbound Twilio call (location TBD)

### Dependencies
- Twilio (already a dependency via `agent/sms.py`/`requirements.txt`)
- Supabase (already a dependency via `agent/db.py`/`requirements.txt`)
- Pipecat Cloud deployment tooling (TBD)

### Risks/Concerns
- Telephony audio quality/latency may differ from WebRTC — needs real-call testing.
- Outbound calling triggers real Twilio costs per form submission — consider abuse protection.
