"""Automated scenario test harness for Ava (Summit Realty Group Gemini Live agent).

Drives the same model/prompt/tools as bot.py with scripted TEXT turns against the
Gemini Live API, captures the spoken reply via output transcription plus any tool
calls (executed against the real mocked functions in tools.py), then asks a plain
Gemini text model to judge each scenario pass/fail against criteria in scenarios.json.

No microphone/audio needed — Gemini Live accepts text input and returns a text
transcript of its audio reply when output_audio_transcription is enabled.

Usage:
    python tests/run_scenarios.py
    python tests/run_scenarios.py --scenario routine_buyer_inquiry
    python tests/run_scenarios.py --judge-model gemini-2.5-flash
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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


async def run_scenario(client: genai.Client, scenario: dict) -> dict:
    config = types.LiveConnectConfig(
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

    turn_records = []

    async with client.aio.live.connect(model=LIVE_MODEL, config=config) as session:
        for user_text in scenario["turns"]:
            await session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=user_text)]),
                turn_complete=True,
            )

            reply_text = ""
            tool_calls = []

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
                        tool_calls.append({"name": fc.name, "args": args, "result": result})
                        responses.append(
                            types.FunctionResponse(name=fc.name, id=fc.id, response=result)
                        )
                    await session.send_tool_response(function_responses=responses)

            turn_records.append(
                {
                    "user": user_text,
                    "reply_transcript": reply_text,
                    "tool_calls": tool_calls,
                }
            )

    return {"scenario_id": scenario["id"], "title": scenario["title"], "turns": turn_records}


async def judge_scenario(client: genai.Client, judge_model: str, scenario: dict, run_result: dict) -> dict:
    transcript_lines = []
    all_tool_calls = []
    for t in run_result["turns"]:
        transcript_lines.append(f"CALLER: {t['user']}")
        transcript_lines.append(f"AVA: {t['reply_transcript']}")
        for tc in t["tool_calls"]:
            all_tool_calls.append(tc["name"])
            transcript_lines.append(f"[tool_call: {tc['name']}({tc['args']}) -> {tc['result']}]")

    expect = scenario["expect"]
    prompt = f"""You are grading a transcript of a real estate lead-qualification AI named Ava.

TRANSCRIPT:
{chr(10).join(transcript_lines)}

EXPECTED TOOLS CALLED (in any order): {expect.get("tools_called", [])}
ACTUAL TOOLS CALLED: {all_tool_calls}
THINGS AVA MUST NOT SAY OR IMPLY: {expect.get("must_not_say", [])}

JUDGE CRITERIA:
{expect["judge_criteria"]}

Respond with ONLY a JSON object (no markdown fences) of the form:
{{"pass": true|false, "triage_observed": "hot"|"normal", "reasons": ["short bullet reasons"]}}
"""

    response = await client.aio.models.generate_content(
        model=judge_model,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )

    try:
        verdict = json.loads(response.text)
    except (json.JSONDecodeError, TypeError):
        verdict = {"pass": False, "triage_observed": "unknown", "reasons": [f"judge returned non-JSON: {response.text!r}"]}

    verdict["tools_called_actual"] = all_tool_calls
    verdict["tools_called_expected"] = expect.get("tools_called", [])
    return verdict


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", help="Run only this scenario id")
    parser.add_argument("--judge-model", default="gemini-2.5-flash")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY not set (check agent/.env)")
        sys.exit(1)

    scenarios_path = Path(__file__).parent / "scenarios.json"
    scenarios = json.loads(scenarios_path.read_text())["scenarios"]

    if args.scenario:
        scenarios = [s for s in scenarios if s["id"] == args.scenario]
        if not scenarios:
            logger.error(f"No scenario with id={args.scenario!r}")
            sys.exit(1)

    client = genai.Client(api_key=api_key)

    run_dir = Path(__file__).parent / "results" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)

    summary = []

    for scenario in scenarios:
        logger.info(f"=== Running scenario: {scenario['id']} ===")
        try:
            run_result = await run_scenario(client, scenario)
        except Exception as e:
            logger.error(f"[{scenario['id']}] failed to run: {e}")
            summary.append({"id": scenario["id"], "title": scenario["title"], "status": "ERROR", "error": str(e)})
            continue

        try:
            verdict = await judge_scenario(client, args.judge_model, scenario, run_result)
        except Exception as e:
            logger.error(f"[{scenario['id']}] judge failed: {e}")
            verdict = {"pass": None, "reasons": [f"judge error: {e}"]}

        out = {"scenario": scenario, "run": run_result, "verdict": verdict}
        (run_dir / f"{scenario['id']}.json").write_text(json.dumps(out, indent=2))

        summary.append(
            {
                "id": scenario["id"],
                "title": scenario["title"],
                "status": "PASS" if verdict.get("pass") else "FAIL" if verdict.get("pass") is False else "UNKNOWN",
                "triage_expected": scenario["expect"].get("triage"),
                "triage_observed": verdict.get("triage_observed"),
                "tools_expected": verdict.get("tools_called_expected"),
                "tools_observed": verdict.get("tools_called_actual"),
                "reasons": verdict.get("reasons", []),
            }
        )

    print("\n" + "=" * 80)
    print(f"{'ID':<35} {'STATUS':<8} {'TRIAGE exp/obs':<22} TOOLS exp/obs")
    print("=" * 80)
    for s in summary:
        if s["status"] == "ERROR":
            print(f"{s['id']:<35} ERROR    {s['error']}")
            continue
        triage = f"{s['triage_expected']}/{s['triage_observed']}"
        print(f"{s['id']:<35} {s['status']:<8} {triage:<22} {s['tools_expected']} / {s['tools_observed']}")
        for r in s["reasons"]:
            print(f"    - {r}")
    print("=" * 80)

    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    logger.info(f"Results written to {run_dir}")


if __name__ == "__main__":
    asyncio.run(main())
