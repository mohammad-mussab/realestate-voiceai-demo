"""Text-chat dev harness for Ava (Summit Realty Group Gemini Live agent).

A fast, text-only alternative to bot.py for iterating on prompts.py/tools.py.
Opens a tiny local web UI (no audio, no microphone) backed by a persistent
Gemini Live session per browser connection. Uses the same connect/send/receive
pattern as tests/run_scenarios.py: text in, output_audio_transcription for
text out, real tool calls against tools.py.

Usage:
    python chat_test.py

Then open http://localhost:7861/ in a browser.
"""

import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from google import genai
from google.genai import types
from loguru import logger

from prompts import SYSTEM_INSTRUCTION
from tools import (
    alert_agent,
    book_appointment,
    capture_lead,
    check_area,
    check_availability,
    qualify_lead,
    send_confirmation_sms,
    transfer_to_human,
)

from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.adapters.services.gemini_adapter import GeminiLLMAdapter

load_dotenv(override=True)

LIVE_MODEL = "gemini-3.1-flash-live-preview"

TOOL_FUNCTIONS = {
    fn.__name__: fn
    for fn in (
        check_area,
        check_availability,
        book_appointment,
        alert_agent,
        capture_lead,
        qualify_lead,
        transfer_to_human,
        send_confirmation_sms,
    )
}


class _FakeFunctionCallParams:
    """Minimal stand-in for pipecat's FunctionCallParams.

    tools.py functions only use .result_callback(...) — they don't read .arguments
    off this object (arguments are passed as kwargs), so this just captures the result.
    """

    def __init__(self):
        self.result = None

    async def result_callback(self, result):
        self.result = result


def build_tools_config():
    tools_schema = ToolsSchema(
        standard_tools=[
            check_area,
            check_availability,
            book_appointment,
            alert_agent,
            capture_lead,
            qualify_lead,
            transfer_to_human,
            send_confirmation_sms,
        ]
    )
    return GeminiLLMAdapter().to_provider_tools_format(tools_schema)


async def call_tool(name: str, args: dict) -> dict:
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        logger.warning(f"Unknown tool called by model: {name}")
        return {"error": f"unknown tool {name}"}

    params = _FakeFunctionCallParams()
    await fn(params, **args)
    return params.result if params.result is not None else {}


def build_live_config() -> types.LiveConnectConfig:
    return types.LiveConnectConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        response_modalities=["AUDIO"],
        output_audio_transcription={},
        tools=build_tools_config(),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=os.environ.get("AGENT_VOICE", "Charon")
                )
            )
        ),
    )


app = FastAPI()


CHAT_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Ava - Chat Test</title>
<style>
  body { font-family: sans-serif; max-width: 700px; margin: 2rem auto; padding: 0 1rem; }
  h1 { font-size: 1.2rem; }
  #log { border: 1px solid #ccc; border-radius: 8px; padding: 1rem; height: 60vh;
         overflow-y: auto; display: flex; flex-direction: column; gap: 0.5rem; }
  .msg { padding: 0.5rem 0.75rem; border-radius: 8px; max-width: 80%; white-space: pre-wrap; }
  .user { background: #d8e8ff; align-self: flex-end; }
  .ava { background: #eee; align-self: flex-start; }
  .tool { background: none; color: #888; font-size: 0.8rem; font-family: monospace;
          align-self: stretch; white-space: pre-wrap; }
  .status { background: none; color: #aaa; font-size: 0.8rem; align-self: center; }
  #form { display: flex; gap: 0.5rem; margin-top: 0.75rem; }
  #input { flex: 1; padding: 0.5rem; font-size: 1rem; }
  #send { padding: 0.5rem 1rem; font-size: 1rem; }
</style>
</head>
<body>
<h1>Ava - Summit Realty Group (chat test)</h1>
<div id="log"></div>
<form id="form">
  <input id="input" type="text" autocomplete="off" placeholder="Type a message..." autofocus>
  <button id="send" type="submit">Send</button>
</form>
<script>
const log = document.getElementById('log');
const form = document.getElementById('form');
const input = document.getElementById('input');

function addMsg(text, cls) {
  const div = document.createElement('div');
  div.className = 'msg ' + cls;
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

const ws = new WebSocket(`ws://${location.host}/ws`);

ws.onopen = () => addMsg('connected - waiting for Ava...', 'status');
ws.onclose = () => addMsg('disconnected', 'status');

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === 'reply') {
    addMsg(msg.text, 'ava');
  } else if (msg.type === 'tool_call') {
    addMsg(`tool: ${msg.name}(${JSON.stringify(msg.args)}) -> ${JSON.stringify(msg.result)}`, 'tool');
  } else if (msg.type === 'status') {
    addMsg(msg.text, 'status');
  }
};

form.addEventListener('submit', (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  addMsg(text, 'user');
  ws.send(JSON.stringify({text}));
  input.value = '';
});
</script>
</body>
</html>
"""


@app.get("/")
async def index():
    return HTMLResponse(CHAT_HTML)


@app.websocket("/ws")
async def chat_ws(websocket: WebSocket):
    await websocket.accept()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        await websocket.send_text(json.dumps({"type": "status", "text": "GEMINI_API_KEY not set"}))
        await websocket.close()
        return

    client = genai.Client(api_key=api_key)
    config = build_live_config()

    try:
        async with client.aio.live.connect(model=LIVE_MODEL, config=config) as session:
            await websocket.send_text(json.dumps({"type": "status", "text": "connected"}))

            while True:
                raw = await websocket.receive_text()
                data = json.loads(raw)
                user_text = data.get("text", "")
                if not user_text:
                    continue

                await session.send_client_content(
                    turns=types.Content(role="user", parts=[types.Part(text=user_text)]),
                    turn_complete=True,
                )

                reply_text = ""
                async for message in session.receive():
                    if message.server_content:
                        sc = message.server_content
                        if sc.output_transcription and sc.output_transcription.text:
                            reply_text += sc.output_transcription.text
                        if sc.turn_complete:
                            break

                    if message.tool_call:
                        responses = []
                        for fc in message.tool_call.function_calls:
                            args = dict(fc.args or {})
                            result = await call_tool(fc.name, args)
                            logger.info(f"[tool_call] {fc.name}({args}) -> {result}")
                            await websocket.send_text(
                                json.dumps({"type": "tool_call", "name": fc.name, "args": args, "result": result})
                            )
                            responses.append(
                                types.FunctionResponse(name=fc.name, id=fc.id, response=result)
                            )
                        await session.send_tool_response(function_responses=responses)

                if reply_text:
                    await websocket.send_text(json.dumps({"type": "reply", "text": reply_text}))
    except WebSocketDisconnect:
        logger.info("Chat client disconnected")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7861)
