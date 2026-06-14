# System Review - Improve Workflow

Review and improve the Claude Code workflow system for the Northgate HVAC demo project.

## Instructions

### Review Areas

1. **Command Effectiveness**
   - Which commands are used frequently?
   - Which commands need improvement?
   - Any missing commands?

2. **Documentation Quality**
   - Is `CLAUDE.md` accurate?
   - Is `docs/hvac_voice_agent_demo.md` (build kit) still aligned with `agent/prompts.py`?
   - Any outdated information?

3. **Workflow Efficiency**
   - Are there repetitive tasks?
   - Can any steps be automated?
   - What causes friction?

4. **Pattern Library**
   - Document new patterns discovered (Pipecat, Gemini Live, Twilio)
   - Update `pipecat-expert` subagent if new conventions emerge
   - Add examples from recent work

### Output
Save to `.agents/system-reviews/{date}.md`:

```markdown
# System Review
Date: {date}

## What's Working
- Item 1
- Item 2

## What Needs Improvement
- Item 1: {suggestion}
- Item 2: {suggestion}

## New Patterns Discovered
- Pattern 1: {description}

## Recommended Changes
1. Change 1
2. Change 2

## Action Items
- [ ] Update command X
- [ ] Add reference doc Y
```

## Usage
```
/system-review
```

Run periodically to keep workflow optimized.
