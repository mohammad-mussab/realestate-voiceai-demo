# Prime - Codebase Analysis

Analyze the codebase to understand patterns, architecture, and conventions.

## Instructions

1. **Read Core Files**
   - Read `CLAUDE.md` for project context
   - Read `agent/bot.py` (pipeline wiring, entry point)
   - Read `agent/prompts.py` (`SYSTEM_INSTRUCTION` — Aria's persona/behavior spec)
   - Read `agent/tools.py` (tool functions + schemas)
   - Read `agent/sms.py` (Twilio SMS helper)

2. **Understand Architecture**
   - Pipeline shape: `transport.input() -> user_aggregator -> GeminiLiveLLMService ->
     transport.output() -> assistant_aggregator`
   - Voice-to-voice via Gemini Live (`gemini-2.5-flash-native-audio-preview-12-2025`) — no
     separate STT/TTS
   - Tools: plain async functions in `agent/tools.py`, registered via
     `register_direct_function` AND listed in `ToolsSchema(standard_tools=[...])`
   - Note testing strategy: `agent/tests/run_scenarios.py` (scripted text-conversation
     scenarios against the real Gemini Live API, graded by an LLM judge)

3. **Document Patterns**
   - Behavior changes (triage logic, tone, flows, hard rules) go in `SYSTEM_INSTRUCTION` in
     `agent/prompts.py`, not code
   - New tools: add to `agent/tools.py` with a docstring `Args:` block, register in both
     places in `agent/bot.py`
   - All tools except `send_confirmation_sms` are mocked (log + fake confirmation)

4. **Output Summary**
   Report:
   - Key architectural decisions
   - Current triage/booking/emergency flow as defined in `SYSTEM_INSTRUCTION`
   - External service integrations (Gemini Live, Twilio SMS)
   - Current state of codebase (any WIP, TODOs, planned features like the outbound-call form)

## Usage
```
/prime
```

After priming, you're ready to plan features or debug issues.
