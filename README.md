# Northgate HVAC Demo Voice Agent

Browser-based voice agent demo for "Northgate Heating & Cooling" built with
[Pipecat](https://github.com/pipecat-ai/pipecat) and Google's Gemini Live API
(`gemini-2.5-flash-native-audio-preview-12-2025`, voice-to-voice — no separate STT/TTS).

## Setup

```bash
cd agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and set GEMINI_API_KEY (Twilio vars optional)
```

## Run

```bash
python bot.py
```

Open `http://localhost:7860/client` in your browser and allow microphone access.

## What it does

- Aria, the receptionist, greets the caller and triages the call as EMERGENCY or ROUTINE.
- Routine calls: checks service area, offers appointment windows, books the visit.
- Emergency calls: captures details fast and escalates to the on-call technician (10 min callback).
- Safety issues (gas/smoke/CO): tells the caller to leave the home and call 911/gas utility first.
- All booking/escalation/lead tools are mocked and logged to the console.
- `send_confirmation_sms` sends a real SMS via Twilio if `TWILIO_*` env vars are set, otherwise
  it logs the message instead.

## Notes

- Requires a microphone-enabled browser (Chrome recommended).
- Conversation transcript is logged to the console via `TranscriptionLogObserver`.
