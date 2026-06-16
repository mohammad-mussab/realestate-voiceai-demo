# Summit Realty Group Demo Voice Agent

Real estate voice-agent demo built with Pipecat and a cascade voice pipeline:

`audio input -> Deepgram Flux STT -> OpenAI LLM -> Cartesia TTS -> audio output`

The agent, Ava, qualifies buyer and seller leads, detects hot leads, books demo
appointments, sends SMS confirmations through Twilio when configured, and logs call
summaries to Supabase when configured.

## Setup

```bash
cd agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set:

- `DEEPGRAM_API_KEY`
- `OPENAI_API_KEY`
- `CARTESIA_API_KEY`
- `CARTESIA_VOICE_ID`

Optional provider defaults:

- `DEEPGRAM_MODEL=flux-general-en`
- `OPENAI_MODEL=gpt-4.1-mini`
- `CARTESIA_MODEL=sonic-3.5`
- `CARTESIA_TEXT_AGGREGATION=token`

## Run

```bash
python bot.py
```

Open `http://localhost:7860/client` in Chrome and allow microphone access.

## Outbound Demo Calls

The Tally webhook in `agent/webhooks.py` extracts the lead name and phone number,
places an outbound Twilio call, and connects Twilio media to the Pipecat `/ws`
endpoint. Configure these env vars for outbound calls:

- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER`
- `PUBLIC_SERVER_URL`
- `DEFAULT_COUNTRY_CODE=+1`
- `BLOCKED_OUTBOUND_COUNTRY_CODES=+91,+92,+977,+880`

By default, outbound demo calls are blocked for India, Pakistan, Nepal, and
Bangladesh phone numbers before Twilio is called.

## Tests

Text scenario tests live in `agent/tests/`:

```bash
cd agent
python tests/run_scenarios.py
python tests/run_scenarios.py --scenario routine_buyer_inquiry
```

They use the OpenAI LLM path, run the same tool functions as the voice bot, and
write results to `agent/tests/results/<timestamp>/`.
