# Execution Report - Document Implementation

Document what was implemented for future reference.

## Instructions

### Input
Feature/task name: $ARGUMENTS

### Report Contents

Generate report in `.agents/execution-reports/{date}-{feature}.md`:

```markdown
# Execution Report: {feature}
Date: {date}
Duration: {approximate}

## Summary
{what was implemented}

## Files Changed
- `agent/prompts.py` - {what changed}
- `agent/tools.py` - {what changed}
- `agent/bot.py` - {what changed}

## Files Created
- `new_file.py` - {purpose}

## Key Decisions
- Decision 1: {rationale}
- Decision 2: {rationale}

## Testing Done
- [ ] `python tests/run_scenarios.py` (full suite / which scenarios)
- [ ] Manual browser check at `http://localhost:7860/client`

## Known Limitations
- Limitation 1 (e.g. tool X remains mocked per demo scope)
- Limitation 2

## Follow-up Tasks
- [ ] Task 1
- [ ] Task 2

## Learnings
{anything worth documenting for future reference}
```

### Auto-populate
- Get changed files from `git diff`
- Extract feature name from plan file if available

## Usage
```
/execution-report outbound-call-form
```
