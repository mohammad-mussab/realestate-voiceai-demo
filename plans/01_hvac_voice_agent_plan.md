# HVAC Voice Agent Demo — Implementation Plan

## Context
Build a demo voice agent for "Northgate Heating & Cooling" (per `docs/hvac_voice_agent_demo.md`)
using Pipecat. Goal: a browser-based phone-call-style demo that proves the concept to an
HVAC business owner — fast, natural turn-taking, correct emergency triage, and a real SMS
confirmation that "wow"s the prospect. Everything else (booking, escalation, leads) is mocked
with logged/printed output — no real CRM/DB.

## Pipecat research summary
Cloned `pipecat-ai/pipecat` to `/tmp/pipecat` and reviewed `examples/realtime/` and
`examples/getting-started/`.

- **Voice-to-voice model**: `OpenAIRealtimeLLMService` (`src/pipecat/services/openai/realtime/llm.py`).
  Default model is **`gpt-realtime-2`** (latest, reasoning-capable) — no separate STT/TTS needed.
- **Pipeline shape** for realtime voice-to-voice (from `examples/realtime/realtime-openai.py`):
  `transport.input() -> user_aggregator -> llm -> transport.output() -> assistant_aggregator`
  (no STT/TTS stages — confirmed, this matches the "brain does voice-to-voice" requirement).
- **Context/tools**: `LLMContext(messages, tools=[...])` with `LLMContextAggregatorPair(context, realtime_service_mode=True)`.
  Tools are plain async Python functions with docstrings (Google-style Args) — Pipecat
  auto-generates the JSON schema from type hints + docstring. Each tool receives
  `params: FunctionCallParams` and calls `await params.result_callback({...})`.
- **Turn detection**: `SessionProperties(audio=AudioConfiguration(input=AudioInput(turn_detection=SemanticTurnDetection(), noise_reduction=InputAudioNoiseReduction(type="near_field"), transcription=InputAudioTranscription())))`.
  Semantic VAD on OpenAI's server gives natural turn-taking (requirement #3 in the spec).
- **Transport for demo**: `SmallWebRTCTransport` + `pipecat_ai_small_webrtc_prebuilt.frontend.SmallWebRTCPrebuiltUI`
  mounted on a FastAPI app (`examples/transports/transports-small-webrtc.py`). Gives a
  ready-made browser mic/speaker UI at `/client` with zero custom frontend work — ideal for
  a demo. Runs locally via `uvicorn`.
- **Worker/runner**: `PipelineWorker` + `WorkerRunner`, kicked off via `on_client_connected`
  event handler queuing `LLMRunFrame()`.
- **Async/slow tools**: `@tool_options(cancel_on_interruption=False)` decorator if a tool needs
  to run long without blocking conversation (not needed here — all tools are instant mocks).

## Architecture for this demo

```
Browser (SmallWebRTC prebuilt UI, mic+speaker)
   <-- WebRTC audio -->
FastAPI app (uvicorn, single process)
   -> SmallWebRTCTransport
   -> Pipeline: transport.input() -> user_aggregator -> OpenAIRealtimeLLMService(gpt-realtime-2) -> transport.output() -> assistant_aggregator
   -> Tools (mocked, in-process Python functions):
        check_service_area   -> always returns covered=true
        check_availability   -> returns 2-3 canned windows
        book_appointment     -> logs booking, returns confirmation
        escalate_emergency   -> logs escalation, returns ack
        capture_lead         -> logs lead
        transfer_to_human    -> logs + returns "transferring" message
        send_confirmation_sms -> REAL Twilio SMS send
```

## Files to create

```
HVAC Demo/
├── docs/hvac_voice_agent_demo.md      (existing, unchanged)
├── plans/01_hvac_voice_agent_plan.md  (this file)
├── pipecat-mcp-server/                (leftover empty dir — remove or ignore)
├── agent/
│   ├── bot.py              # FastAPI app + SmallWebRTC setup + pipeline wiring (entry point)
│   ├── prompts.py          # SYSTEM_INSTRUCTION constant, adapted from docs/ spec
│   ├── tools.py            # all tool functions (check_service_area, book_appointment, etc.)
│   ├── sms.py               # Twilio SMS helper used by send_confirmation_sms
│   ├── .env.example         # OPENAI_API_KEY, TWILIO_* vars
│   └── requirements.txt     # pipecat-ai[openai,webrtc], pipecat-ai-small-webrtc-prebuilt, fastapi, uvicorn, twilio, python-dotenv, loguru
└── README.md                 # how to run the demo
```

## Implementation details

### 1. `prompts.py`
Port the system prompt from `docs/hvac_voice_agent_demo.md` almost verbatim, filling in
placeholders: `[CITY]` -> a chosen demo city (e.g., "Toronto"), `[X]` -> "15-20 minutes" for
emergency callback time. Keep all the voice-style rules (short replies, one question at a
time, no markdown, read back numbers, hard rules on pricing/diagnosis).

### 2. `tools.py` — mocked tool functions
Each is an `async def name(params: FunctionCallParams, ...)` with a docstring (Args section)
matching the parameter schemas in the spec section 2. Implementation per spec section 3:

- `check_service_area(params, city, postal_code=None)` -> always `{"covered": True, "city": city}`
- `check_availability(params, preferred_date, urgency)` -> returns a fixed list of 2-3 windows,
  e.g. `["tomorrow morning (8am-12pm)", "tomorrow afternoon (12pm-4pm)", "Thursday morning (8am-12pm)"]`
  (vary slightly if `urgency == "emergency"` to bias toward sooner windows)
- `book_appointment(params, name, phone, address, issue_description, appointment_window, city=None, postal_code=None, job_type=None)`
  -> logs the booking via `loguru.logger.info` (clearly formatted "BOOKING CREATED" block) and
  returns a confirmation dict with a fake booking ID (e.g. `f"NG-{random 4 digits}"`)
- `escalate_emergency(params, name, phone, address, issue_description, safety_flag=False)`
  -> logs "EMERGENCY ESCALATION" block, returns ack with fake ticket ID + ETA
- `capture_lead(params, phone, name=None, reason=None)` -> logs "LEAD CAPTURED", returns ack
- `transfer_to_human(params, reason)` -> logs "TRANSFER REQUESTED", returns a message the
  model should relay (demo: no real transfer, just acknowledges)
- `send_confirmation_sms(params, phone, message)` -> **real** Twilio send via `sms.py` helper;
  catches/logs errors gracefully so the demo doesn't crash if Twilio isn't configured (falls
  back to logging the message if Twilio env vars are missing)

### 3. `sms.py`
Thin wrapper around `twilio.rest.Client`. Reads `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
`TWILIO_FROM_NUMBER` from env. `send_sms(to: str, body: str) -> dict` returns
`{"sent": True/False, "sid": ..., "error": ...}`.

### 4. `bot.py`
Mirrors `examples/transports/transports-small-webrtc.py`:
- FastAPI app, mounts `SmallWebRTCPrebuiltUI` at `/client`, `/api/offer` endpoint, lifespan cleanup.
- `run_bot(webrtc_connection)`:
  - `SmallWebRTCTransport(webrtc_connection, TransportParams(audio_in_enabled=True, audio_out_enabled=True))`
  - `OpenAIRealtimeLLMService(api_key=OPENAI_API_KEY, settings=Settings(model="gpt-realtime-2", system_instruction=SYSTEM_INSTRUCTION, session_properties=SessionProperties(audio=AudioConfiguration(input=AudioInput(turn_detection=SemanticTurnDetection(), noise_reduction=InputAudioNoiseReduction(type="near_field"), transcription=InputAudioTranscription())))))`
  - `context = LLMContext(tools=[check_service_area, check_availability, book_appointment, escalate_emergency, capture_lead, transfer_to_human, send_confirmation_sms])`
  - `user_aggregator, assistant_aggregator = LLMContextAggregatorPair(context, realtime_service_mode=True)`
  - Pipeline: `[transport.input(), user_aggregator, llm, transport.output(), assistant_aggregator]`
  - `PipelineWorker(pipeline, params=PipelineParams(enable_metrics=True, enable_usage_metrics=True), observers=[TranscriptionLogObserver()])`
  - `on_client_connected`: queue `LLMRunFrame()` so Aria speaks the opening line first (the
    system prompt already defines the opening line, so the model should greet on its own —
    add a developer message "Greet the caller with your opening line" to be safe)
  - `on_client_disconnected`: `worker.cancel()`

### 5. `requirements.txt` / `.env.example`
- `pipecat-ai[openai,webrtc]`, `pipecat-ai-small-webrtc-prebuilt`, `fastapi`, `uvicorn[standard]`,
  `python-dotenv`, `loguru`, `twilio`
- `.env.example`: `OPENAI_API_KEY=`, `TWILIO_ACCOUNT_SID=`, `TWILIO_AUTH_TOKEN=`, `TWILIO_FROM_NUMBER=`

### 6. README.md
Quick setup: create venv, install requirements, copy `.env.example` -> `.env` and fill keys,
`python agent/bot.py`, open `http://localhost:7860/client`. Note mic permission needed in browser.

## Verification
1. `pip install -r agent/requirements.txt`, set `OPENAI_API_KEY` (and Twilio vars, optional).
2. `python agent/bot.py`, open `http://localhost:7860/client` in browser, allow mic.
3. Test routine flow: state a noisy-furnace complaint -> agent should triage as routine, ask
   one question at a time (name, phone, address, issue, time window), call
   `check_service_area` + `check_availability` + `book_appointment`, read back confirmation.
4. Test emergency flow: say "no heat and it's freezing" -> agent should treat as emergency,
   capture details fast, call `escalate_emergency`.
5. Test safety flow: mention "gas smell" -> agent should tell caller to leave home/call
   911/gas utility first, then capture details.
6. If Twilio configured, confirm a real SMS arrives when `send_confirmation_sms` is called;
   if not configured, confirm it logs gracefully without crashing the pipeline.
7. Check console/logs for the mocked "BOOKING CREATED" / "EMERGENCY ESCALATION" / etc. blocks.

## Open questions
- Demo city/business name: use "Toronto" + "Northgate Heating & Cooling" as in spec, or change? Default: keep as-is.
- Emergency callback ETA ([X] minutes): default to 15-20 min — ok?
- Twilio: do you have a Twilio trial account/number ready, or should SMS fall back to log-only for now?
- `pipecat-mcp-server/` empty dir — delete it, or is something supposed to go there?

