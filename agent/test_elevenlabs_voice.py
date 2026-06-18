"""One-off script: verify ELEVENLABS_VOICE_ID actually returns audio.

Usage: python test_elevenlabs_voice.py
Writes test_elevenlabs_output.mp3 on success.
"""

import os

import httpx
from dotenv import load_dotenv

load_dotenv(override=True)

api_key = os.environ["ELEVENLABS_API_KEY"]
voice_id = os.environ["ELEVENLABS_VOICE_ID"]
model = os.environ.get("ELEVENLABS_MODEL", "eleven_flash_v2_5")

print(f"Testing voice_id={voice_id} model={model}")

resp = httpx.post(
    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
    headers={"xi-api-key": api_key, "Content-Type": "application/json"},
    json={
        "text": "Hello, this is a test of the voice.",
        "model_id": model,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    },
    timeout=30,
)

print("Status:", resp.status_code)
print("Content-Type:", resp.headers.get("content-type"))
print("Bytes received:", len(resp.content))

if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("audio"):
    with open("test_elevenlabs_output.mp3", "wb") as f:
        f.write(resp.content)
    print("SUCCESS: wrote test_elevenlabs_output.mp3")
else:
    print("FAILED response body:", resp.text[:1000])
