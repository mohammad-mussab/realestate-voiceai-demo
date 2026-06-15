"""Automated scenario test harness for Ava (Summit Realty Group OpenAI agent).

Drives the same prompt/tools as bot.py through scripted TEXT turns against the
OpenAI Chat Completions API, captures replies plus tool calls, then asks an
OpenAI judge model to grade each scenario pass/fail against scenarios.json.

Usage:
    python tests/run_scenarios.py
    python tests/run_scenarios.py --scenario routine_buyer_inquiry
    python tests/run_scenarios.py --model gpt-4.1-mini --judge-model gpt-4.1-mini
"""

import argparse
import asyncio
import inspect
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from openai import AsyncOpenAI

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
from pipecat.adapters.services.open_ai_adapter import OpenAILLMAdapter

load_dotenv(override=True)

DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
DEFAULT_JUDGE_MODEL = os.environ.get("OPENAI_JUDGE_MODEL", DEFAULT_MODEL)
DEFAULT_SCENARIO_TEMPERATURE = float(os.environ.get("SCENARIO_OPENAI_TEMPERATURE", "0.0"))

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
    if name == "send_confirmation_sms":
        logger.info(f"[test stub] send_confirmation_sms({args})")
        return {"sent": True, "sid": "TEST-SMS", "error": None, "test_mode": True}

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


def _tool_call_message(tool_call, result: dict) -> dict:
    return {
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": json.dumps(result),
    }


async def complete_turn(client: AsyncOpenAI, model: str, messages: list[dict], tools: list[dict]):
    reply_text = ""
    tool_calls = []

    while True:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=DEFAULT_SCENARIO_TEMPERATURE,
            max_completion_tokens=int(os.environ.get("OPENAI_MAX_COMPLETION_TOKENS", "180")),
        )
        message = response.choices[0].message

        if message.tool_calls:
            messages.append(message.model_dump(exclude_none=True))
            for tc in message.tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                result = await call_tool(tc.function.name, args)
                tool_calls.append({"name": tc.function.name, "args": args, "result": result})
                messages.append(_tool_call_message(tc, result))
            continue

        reply_text = message.content or ""
        messages.append({"role": "assistant", "content": reply_text})
        return reply_text, tool_calls


async def run_scenario(client: AsyncOpenAI, model: str, scenario: dict) -> dict:
    messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
    tools = build_tools_config()
    turn_records = []

    for user_text in scenario["turns"]:
        messages.append({"role": "user", "content": user_text})
        reply_text, tool_calls = await complete_turn(client, model, messages, tools)
        turn_records.append(
            {
                "user": user_text,
                "reply_transcript": reply_text,
                "tool_calls": tool_calls,
            }
        )

    return {"scenario_id": scenario["id"], "title": scenario["title"], "turns": turn_records}


async def judge_scenario(client: AsyncOpenAI, judge_model: str, scenario: dict, run_result: dict) -> dict:
    transcript_lines = []
    all_tool_calls = []
    for turn in run_result["turns"]:
        transcript_lines.append(f"CALLER: {turn['user']}")
        transcript_lines.append(f"AVA: {turn['reply_transcript']}")
        for tool_call in turn["tool_calls"]:
            all_tool_calls.append(tool_call["name"])
            transcript_lines.append(
                f"[tool_call: {tool_call['name']}({tool_call['args']}) -> {tool_call['result']}]"
            )

    expect = scenario["expect"]
    prompt = f"""You are grading a transcript of a real estate lead-qualification AI named Ava.

TRANSCRIPT:
{chr(10).join(transcript_lines)}

EXPECTED TOOLS CALLED (in any order): {expect.get("tools_called", [])}
ACTUAL TOOLS CALLED: {all_tool_calls}
THINGS AVA MUST NOT SAY OR IMPLY: {expect.get("must_not_say", [])}

JUDGE CRITERIA:
{expect["judge_criteria"]}

Extra send_confirmation_sms calls after a successful booking are allowed and should not cause
failure by themselves, because the production prompt sends booking confirmations by SMS.

Respond with ONLY a JSON object of the form:
{{"pass": true|false, "triage_observed": "hot"|"normal", "reasons": ["short bullet reasons"]}}
"""

    response = await client.chat.completions.create(
        model=judge_model,
        messages=[
            {"role": "system", "content": "You are a strict JSON-only evaluator."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    text = response.choices[0].message.content or "{}"
    try:
        verdict = json.loads(text)
    except json.JSONDecodeError:
        verdict = {"pass": False, "triage_observed": "unknown", "reasons": [f"judge returned non-JSON: {text!r}"]}

    verdict["tools_called_actual"] = all_tool_calls
    verdict["tools_called_expected"] = expect.get("tools_called", [])
    return verdict


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", help="Run only this scenario id")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not set (check agent/.env)")
        sys.exit(1)

    scenarios_path = Path(__file__).parent / "scenarios.json"
    scenarios = json.loads(scenarios_path.read_text())["scenarios"]

    if args.scenario:
        scenarios = [s for s in scenarios if s["id"] == args.scenario]
        if not scenarios:
            logger.error(f"No scenario with id={args.scenario!r}")
            sys.exit(1)

    client = AsyncOpenAI(api_key=api_key)

    run_dir = Path(__file__).parent / "results" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)

    summary = []

    for scenario in scenarios:
        logger.info(f"=== Running scenario: {scenario['id']} ===")
        try:
            run_result = await run_scenario(client, args.model, scenario)
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
    for item in summary:
        if item["status"] == "ERROR":
            print(f"{item['id']:<35} ERROR    {item['error']}")
            continue
        triage = f"{item['triage_expected']}/{item['triage_observed']}"
        print(f"{item['id']:<35} {item['status']:<8} {triage:<22} {item['tools_expected']} / {item['tools_observed']}")
        for reason in item["reasons"]:
            print(f"    - {reason}")
    print("=" * 80)

    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    logger.info(f"Results written to {run_dir}")


if __name__ == "__main__":
    asyncio.run(main())
