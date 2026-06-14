# Implement Fix - Apply Bug Fix from RCA

Implement a bug fix based on completed root cause analysis.

## Instructions

### Input
RCA document path or issue description: $ARGUMENTS

### Process

1. **Load RCA**
   - Read RCA from `.claude/docs/rca-{issue}.md` if one exists
   - Verify root cause is documented
   - Review proposed fix

2. **Implement Fix**
   - Make minimal changes
   - Follow project conventions (behavior fixes go in `agent/prompts.py`
     `SYSTEM_INSTRUCTION`; tool/code fixes go in `agent/tools.py` or `agent/bot.py`)
   - Don't refactor unrelated code

3. **Test Fix**
   - Run `python tests/run_scenarios.py --scenario {relevant_scenario}` (or the full suite)
   - chat_test.py (text-only local test) once available
   - Verify symptom is resolved
   - Check for regressions

4. **Validate**
   - Run `/validate`
   - Ensure no new issues

5. **Document**
   Update or create the RCA doc with:
   - Fix applied
   - Testing results
   - Any follow-up needed

### Commit Message Format
```
fix: {brief description}

Root cause: {one line}
```

## Usage
```
/implement-fix rca-emergency-triage-missed-gas-smell
/implement-fix Aria books appointments without calling check_availability first
```

After implementing, run `/code-review` before committing.
