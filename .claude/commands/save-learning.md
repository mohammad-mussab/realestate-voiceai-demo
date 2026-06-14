# Save Learning

Capture important learnings from a completed task or debugging session.

## Purpose
Build a project-specific knowledge base that Claude checks BEFORE researching from scratch.
This prevents solving the same problem twice.

## Process

### Step 1: Identify the Learning
Determine:
- What category? (pipecat, gemini-live, twilio, prompt-tuning, pipecat-cloud)
- What's the core lesson?
- What problem does this solve?

### Step 2: Create Learning Document
Create file at `docs/{category}/{descriptive-name}.md`

### Step 3: Document Structure
```markdown
# {Title}

## Problem
What issue or challenge was encountered?

## Solution
How was it solved? Include code snippets if relevant.

## Key Code Reference
Which files in our project implement this?
- `agent/{file}.py` - lines X-Y

## Gotchas
What to watch out for?

## Date Learned
{date}

## Related
Links to related learnings or external docs
```

### Step 4: Update Sub-Agent Awareness
If this learning is critical, consider updating `pipecat-expert` in `.claude/agents/` to
explicitly check for this document.

## Categories

| Category | Use For |
|----------|---------|
| `pipecat` | Framework patterns, pipeline wiring, transport configs, Pipecat Cloud deployment |
| `gemini-live` | Gemini Live voice-to-voice quirks (voices, turn detection, session config) |
| `twilio` | SMS sending, outbound calling (future), phone number handling |
| `prompt-tuning` | What wording in `SYSTEM_INSTRUCTION` did/didn't work for triage, tool-calling discipline, voice tone |

## Arguments
$ARGUMENTS - Brief description of what was learned

## Example Usage
```
/save-learning Discovered Gemini Live drops the session if system_instruction exceeds ~N
tokens — keep SYSTEM_INSTRUCTION concise. Category: gemini-live
```
