# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Browser-based voice agent demo for "Summit Realty Group" (fictional real estate brokerage),
built with [Pipecat](https://github.com/pipecat-ai/pipecat) and a cascade voice pipeline:
Deepgram Flux STT -> OpenAI Chat LLM -> Cartesia TTS. The agent ("Ava") answers calls,
qualifies buyer/seller leads, detects hot leads, and books showings/listing consultations.

## Setup & run

```bash
cd agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and set DEEPGRAM_API_KEY, OPENAI_API_KEY, CARTESIA_API_KEY,
# and CARTESIA_VOICE_ID (Twilio + Supabase vars optional)
python bot.py
```

Open `http://localhost:7860/client` in a browser (Chrome recommended) and allow microphone
access. There is no lint config — verification is manual via the browser client and console logs,
plus the automated scenario tests below.

## Automated scenario tests

`agent/tests/` drives Ava through scripted text conversations against OpenAI using the same
prompt and tool functions as the voice bot, then uses an LLM judge to grade each scenario
pass/fail.

```bash
cd agent
source .venv/bin/activate
python tests/run_scenarios.py                          # all scenarios in tests/scenarios.json
python tests/run_scenarios.py --scenario routine_buyer_inquiry   # single scenario
```

Results (full transcripts, tool calls, judge verdicts) are written to
`agent/tests/results/<timestamp>/`. Edit `agent/tests/scenarios.json` to add/adjust scenarios —
each has `turns` (scripted caller lines) and `expect` (triage, expected tools, things Ava must
not say, judge criteria).

## Architecture

- `agent/bot.py` — entry point. Builds the Pipecat pipeline: WebRTC transport ->
  `DeepgramFluxSTTService` -> `LLMContextAggregatorPair` -> `OpenAILLMService` ->
  `CartesiaTTSService` -> transport output. Registers all tool functions on the LLM and in the
  `ToolsSchema`. On `on_client_connected`, injects a developer message telling Ava to greet the
  caller and kicks off the pipeline with `LLMRunFrame()`. A `CallSummaryObserver` accumulates
  lead/qualification/booking details from tool-call results during the call; on
  `on_client_disconnected`, the accumulated summary is logged to Supabase via `agent/db.py`.
- `agent/prompts.py` — `SYSTEM_INSTRUCTION`, the full persona/behavior spec for Ava (identity,
  speaking style, buyer/seller qualifying flow, hot-lead detection, info-capture flow, booking
  flow, hard rules including fair housing, opening line). This is the primary "brain" of the
  agent — most behavior changes happen here, not in code.
- `agent/tools.py` — tool functions called by the LLM (`check_area`, `check_availability`,
  `book_appointment`, `alert_agent`, `capture_lead`, `qualify_lead`, `transfer_to_human`,
  `send_confirmation_sms`). Each function's docstring (Args section) is the source of truth
  for its tool schema — Pipecat derives the schema from the signature and docstring. All tools
  except `send_confirmation_sms` are mocked: they log a formatted block to the console via
  `loguru` and return a fake confirmation (e.g. `book_appointment` generates a random
  `SRG-####` booking ID, `alert_agent` generates a `SRG-LEAD-####` ticket ID).
- `agent/sms.py` — `send_sms()` thin Twilio wrapper. Sends a real SMS if
  `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN`/`TWILIO_FROM_NUMBER` are set in `.env`, otherwise
  logs the message instead of sending.
- `agent/db.py` — `log_call()` thin Supabase wrapper. Inserts a row into the `call_logs` table
  if `SUPABASE_URL`/`SUPABASE_KEY` are set in `.env`, otherwise logs the summary instead of
  saving.
- `TranscriptionLogObserver` (from Pipecat) logs the full conversation transcript to the console.
- All logs (DEBUG level, including transcripts and tool-call arguments/results) are also written
  to `agent/logs/bot_<date>.log` (rotated daily, kept 14 days) via a loguru file sink in `bot.py`.

## Working in this repo

- This is a demo, not production: tool implementations are intentionally mocked/fake except SMS
  and Supabase call logging. Don't add real CRM/MLS integrations unless asked — see
  `plans/realt_estate_agent_plan.md` for the demo-vs-production breakdown per tool.
- When changing agent behavior (qualifying logic, tone, flows, hard rules), edit
  `SYSTEM_INSTRUCTION` in `agent/prompts.py` rather than adding code-side logic.
- When adding a new tool, add the async function to `agent/tools.py` (with a docstring `Args:`
  block matching the param types — this generates the schema), then register it in both places
  in `agent/bot.py`: the `llm.register_direct_function(...)` loop and the
  `ToolsSchema(standard_tools=[...])` list. Tool functions take the form
  `async def fn(params: FunctionCallParams, arg1: str, ...)` — these are "direct functions" and
  MUST be registered with `register_direct_function`, not `register_function` (the latter calls
  the handler with only `params`, dropping all LLM-provided arguments).
- Keep prompt language voice-appropriate: short replies, one question at a time, no
  lists/markdown/emojis (the text is spoken aloud via TTS).
