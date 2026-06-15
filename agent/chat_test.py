"""Text-chat dev harness for Ava (Summit Realty Group OpenAI agent).

A fast, text-only alternative to bot.py for iterating on prompts.py/tools.py.
Opens a tiny local web UI backed by OpenAI Chat Completions with the same prompt
and tool functions used by the cascade voice bot.

Usage:
    python chat_test.py

Then open http://localhost:7861/ in a browser.
"""

import inspect
import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from loguru import logger
from openai import AsyncOpenAI

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
from pipecat.adapters.services.open_ai_adapter import OpenAILLMAdapter

load_dotenv(override=True)

DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

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
    """Minimal stand-in for pipecat's FunctionCallParams."""

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
    return OpenAILLMAdapter().to_provider_tools_format(tools_schema)


async def call_tool(name: str, args: dict) -> dict:
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        logger.warning(f"Unknown tool called by model: {name}")
        return {"error": f"unknown tool {name}"}

    signature = inspect.signature(fn)
    allowed_args = {key for key in signature.parameters if key != "params"}
    extra_args = sorted(set(args) - allowed_args)
    if extra_args:
        logger.warning(f"Ignoring extra args for {name}: {extra_args}")
    filtered_args = {key: value for key, value in args.items() if key in allowed_args}

    params = _FakeFunctionCallParams()
    await fn(params, **filtered_args)
    return params.result if params.result is not None else {}


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


def _tool_message(tool_call, result: dict) -> dict:
    return {
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": json.dumps(result),
    }


async def complete_turn(client: AsyncOpenAI, websocket: WebSocket, messages: list[dict], tools: list[dict]) -> str:
    while True:
        response = await client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=float(os.environ.get("OPENAI_TEMPERATURE", "0.3")),
            max_completion_tokens=int(os.environ.get("OPENAI_MAX_COMPLETION_TOKENS", "180")),
        )
        message = response.choices[0].message

        if message.tool_calls:
            messages.append(message.model_dump(exclude_none=True))
            for tool_call in message.tool_calls:
                args = json.loads(tool_call.function.arguments or "{}")
                result = await call_tool(tool_call.function.name, args)
                logger.info(f"[tool_call] {tool_call.function.name}({args}) -> {result}")
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "tool_call",
                            "name": tool_call.function.name,
                            "args": args,
                            "result": result,
                        }
                    )
                )
                messages.append(_tool_message(tool_call, result))
            continue

        reply = message.content or ""
        messages.append({"role": "assistant", "content": reply})
        return reply


@app.websocket("/ws")
async def chat_ws(websocket: WebSocket):
    await websocket.accept()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        await websocket.send_text(json.dumps({"type": "status", "text": "OPENAI_API_KEY not set"}))
        await websocket.close()
        return

    client = AsyncOpenAI(api_key=api_key)
    tools = build_tools_config()
    messages = [
        {"role": "system", "content": SYSTEM_INSTRUCTION},
        {"role": "developer", "content": "Greet the caller with your opening line now."},
    ]

    try:
        await websocket.send_text(json.dumps({"type": "status", "text": f"connected ({DEFAULT_MODEL})"}))
        opening = await complete_turn(client, websocket, messages, tools)
        if opening:
            await websocket.send_text(json.dumps({"type": "reply", "text": opening}))

        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            user_text = data.get("text", "")
            if not user_text:
                continue

            messages.append({"role": "user", "content": user_text})
            reply = await complete_turn(client, websocket, messages, tools)
            if reply:
                await websocket.send_text(json.dumps({"type": "reply", "text": reply}))
    except WebSocketDisconnect:
        logger.info("Chat client disconnected")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7861)
