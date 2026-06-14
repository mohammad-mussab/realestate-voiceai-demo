# Code Review - Review Changed Files

Review code changes for quality, patterns, and potential issues.

## Instructions

### Review Scope
Files to review: $ARGUMENTS (or staged/modified files if not specified)

### Review Checklist

1. **Code Quality**
   - [ ] Follows project naming conventions
   - [ ] No hardcoded secrets (use `.env` / `os.environ`)
   - [ ] Proper async/await usage
   - [ ] No security vulnerabilities

2. **Pipecat / Project Patterns**
   - [ ] Tool functions are `async def fn(params: FunctionCallParams, ...)` with a docstring
     `Args:` block matching parameter types
   - [ ] New/changed tools registered in BOTH places in `agent/bot.py`:
     `register_direct_function` loop and `ToolsSchema(standard_tools=[...])`
   - [ ] Direct functions use `register_direct_function`, not `register_function`
   - [ ] Behavior changes (triage, tone, flows, hard rules) live in `SYSTEM_INSTRUCTION`
     (`agent/prompts.py`), not hardcoded in pipeline code

3. **Voice / Prompt Quality** (if `agent/prompts.py` changed)
   - [ ] No lists, bullet points, symbols, emojis, or markdown in spoken text
   - [ ] Short replies, one question at a time
   - [ ] No exact prices or specific dollar ranges
   - [ ] No technical diagnosis/repair instructions

4. **Demo Scope**
   - [ ] Mocked tools stay mocked (log + fake confirmation) unless the change explicitly adds
     a real integration (see `docs/hvac_voice_agent_demo.md` section 3)
   - [ ] `send_confirmation_sms` remains the only real integration (Twilio), with graceful
     fallback to logging if Twilio env vars are unset

5. **Testing Considerations**
   - [ ] Can be tested via `python tests/run_scenarios.py`
   - [ ] New scenarios added to `agent/tests/scenarios.json` if behavior changed

### Output
Save review to `.agents/code-reviews/{date}-{branch}.md`:
```markdown
# Code Review: {description}
Date: {date}
Files: {list}

## Summary
{overview}

## Issues Found
- [ ] Issue 1 (severity: high/medium/low)
- [ ] Issue 2

## Suggestions
- Suggestion 1
- Suggestion 2

## Verdict
APPROVED / NEEDS CHANGES
```

## Usage
```
/code-review
/code-review agent/tools.py
```
