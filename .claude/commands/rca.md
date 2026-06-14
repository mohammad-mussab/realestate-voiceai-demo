# RCA - Root Cause Analysis (Agent Log Debugging)

Debug the Northgate HVAC voice agent (Aria) by analyzing log files. Optimized for large log
files — never reads full logs, uses smart targeted search.

## Instructions

### Input
$ARGUMENTS — Describe the problem observed (e.g., "Aria books an appointment without calling
check_availability", "bot goes silent after caller gives address", "emergency not escalated
for gas smell")

### Log Location
- `agent/logs/bot_<date>.log` (DEBUG level, rotated daily, kept 14 days) — includes full
  transcript, tool-call arguments/results, and pipeline frame activity via
  `TranscriptionLogObserver`
- Scenario test results: `agent/tests/results/<timestamp>/` (full transcripts, tool calls,
  judge verdicts) if the issue reproduces via `python tests/run_scenarios.py`

### CRITICAL: Smart Log Search Strategy

**NEVER read the full log file.** Log files can be large. Instead:

1. **Start with errors** — Grep for `ERROR|CRITICAL|Exception|Traceback|failed|failure` first
2. **Narrow by timestamp** — If user provides a time range, grep for that timestamp prefix
   first, then read ±20 lines around matches
3. **Targeted reads only** — After grep finds line numbers, use `Read` with `offset` + `limit`
   (max 50-100 lines per read)
4. **Work top-down** — Start broad (errors), then narrow to specific patterns based on findings

### Debugging Process

#### Phase 1: Triage (30 seconds)
Grep the log file for critical issues in this order:

```
# 1. Fatal errors & exceptions
grep: ERROR|CRITICAL|Exception|Traceback|fatal error

# 2. Pipeline/worker health
grep: Idle timeout|pipeline.*cancel|Something went wrong|worker.*error

# 3. Connection failures (Gemini Live / WebRTC)
grep: Connection lost|connection error|will retry|disconnected|Client connected|Client disconnected
```

If any of these hit, read ±15 lines of context around the match. This alone solves most issues.

#### Phase 2: Layer-by-Layer Diagnosis

**Layer 1 — Transport (WebRTC)**
```
grep: Client connected|Client disconnected|on_client_connected|on_client_disconnected
```
Issues: connection drops, audio not flowing.

**Layer 2 — Gemini Live (voice-to-voice LLM)**
```
grep: GeminiLiveLLMService|session|UserStartedSpeakingFrame|UserStoppedSpeakingFrame
grep: TranscriptionFrame
```
Issues: no transcription, model not responding, turn-taking problems.

**Layer 3 — Tool Calls**
```
grep: check_service_area|check_availability|book_appointment|escalate_emergency|capture_lead|transfer_to_human|send_confirmation_sms
grep: BOOKING CREATED|EMERGENCY ESCALATION|LEAD CAPTURED|TRANSFER REQUESTED
grep: function_call|Function called
```
Issues: wrong tool selected, tool not called when it should be, wrong arguments passed (check
against the docstring `Args:` schema in `agent/tools.py`).

**Layer 4 — SMS (Twilio)**
```
grep: SMS sent|SMS failed|SMS - NOT SENT
```
Issues: Twilio not configured (expected if `.env` lacks `TWILIO_*` — `sms.py` falls back to
logging), or real send failure.

#### Phase 3: Behavior / Triage Analysis
Most "wrong behavior" bugs (Aria says the wrong thing, skips a tool call, gives a price, etc.)
are prompt issues, not code bugs:

1. Find the relevant turn in the transcript (search for the caller's line)
2. Compare Aria's response/tool calls against the relevant section of `SYSTEM_INSTRUCTION` in
   `agent/prompts.py` (TRIAGE, BOOKING FLOW, EMERGENCY FLOW, HARD RULES)
3. If the rule exists in the prompt but wasn't followed -> note as a prompt-following issue
   (may need stronger/clearer wording, not new code)
4. If the rule doesn't exist -> note as a missing-rule issue

#### Phase 4: Performance Analysis
```
# Latency metrics (enabled via PipelineParams(enable_metrics=True))
grep: TTFB|processing time

# Token usage (enable_usage_metrics=True)
grep: LLMUsageMetrics|prompt_tokens|completion_tokens
```

### Common Failure Patterns & What They Mean

| Pattern in Logs | Root Cause | Fix Direction |
|----------------|------------|---------------|
| Rapid reconnect loops (connect/disconnect within 5s) | Bad `GEMINI_API_KEY` or config mismatch | Check `.env`, API key validity |
| No tool call logged after "let me check"/"I'll book that" | Aria said it but didn't call the tool | Strengthen the relevant rule in `SYSTEM_INSTRUCTION` (see "NEVER say ... without actually calling the matching tool" rule) |
| `book_appointment` called without prior `check_availability` | Aria invented a time window | Reinforce BOOKING FLOW ordering in `agent/prompts.py` |
| `escalate_emergency` not called for an emergency-trigger phrase | TRIAGE rule missing/unclear for that phrase | Add/clarify the trigger in the TRIAGE section |
| `[SMS - NOT SENT, Twilio not configured]` | `TWILIO_*` env vars unset | Expected in dev; set vars in `.env` if real SMS needed |
| `[SMS failed]` with an exception | Real Twilio call failed | Check Twilio credentials/from-number validity |
| No frames after a timestamp | Pipeline died silently | Check for uncaught exception just before that point |
| Aria gives an exact price/dollar range | HARD RULES violation | Check wording of the pricing hard rule in `agent/prompts.py` |

### Output Format

After analysis, present findings as:

```markdown
## RCA: {issue title}
Date: {date}

## Symptoms
{what was observed}

## Log Evidence
{specific log lines with line numbers that prove the root cause}

## Root Cause
{technical explanation — what happened and why}

## Location
- File: {path, e.g. agent/prompts.py or agent/tools.py}
- Section/Function: {name}
- Line: ~{approximate}

## Proposed Fix
{minimal fix description}

## Files to Modify
- agent/prompts.py
- agent/tools.py
```

### Tips & Tricks

1. **Timestamps are your friend** — if the issue happened at a specific time, grep for that
   minute first, then expand
2. **Compare good vs bad** — if you have logs/transcripts from a working call AND a broken
   call, diff the transcript and tool-call sequence
3. **Count occurrences** — `grep -c "pattern"` reveals if something happened 0 times (missing)
   or repeatedly (loop)
4. **Check the gaps** — if the caller speaks but no `TranscriptionFrame`/response follows,
   audio or the Gemini Live session likely dropped
5. **Scenario tests reproduce reliably** — if the bug is behavioral, try to reproduce it as a
   new entry in `agent/tests/scenarios.json` so it's caught automatically going forward

## Usage
```
/rca Aria offers a time window without calling check_availability
/rca Caller mentions gas smell but Aria doesn't tell them to leave the house
/rca Bot goes silent after the caller gives their address
```

After RCA, use `/implement-fix` to apply the solution.
