# Execute - Implement Plan Step-by-Step

Execute an approved plan from `.claude/plans/`.

## Instructions

### Input
Plan file path or feature name: $ARGUMENTS

### Execution Process

1. **Load Plan**
   - Read plan from `.claude/plans/{feature}.md`
   - Verify plan exists and has approval

2. **Execute Steps Sequentially**
   For each step in the plan:
   - Announce current step
   - Implement the change
   - Run quick validation if applicable
   - Mark step complete in todo list

3. **Follow Project Conventions**
   - Behavior changes (triage, tone, flows, hard rules) go in `SYSTEM_INSTRUCTION` in
     `agent/prompts.py`, not code
   - New tools: `async def fn(params: FunctionCallParams, ...)` with a docstring `Args:` block
     in `agent/tools.py`, registered in BOTH the `register_direct_function` loop and
     `ToolsSchema(standard_tools=[...])` in `agent/bot.py`
   - Keep prompt language voice-appropriate: short replies, one question at a time, no
     lists/markdown/emojis
   - Tools other than `send_confirmation_sms` stay mocked (log + fake confirmation) unless the
     plan explicitly calls for a real integration

4. **Testing After Implementation**
   - Run `python tests/run_scenarios.py --scenario {relevant_scenario}` for quick validation
     (or `python tests/run_scenarios.py` for the full suite)
   - chat_test.py (text-only local test) once available
   - Document any issues found

5. **Update Plan Status**
   Mark completed steps in plan file.

## Usage
```
/execute outbound-call-form
```

## Post-Execution
After completing, run `/validate` to verify changes.
