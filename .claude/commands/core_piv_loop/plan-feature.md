# Plan Feature - Implementation Planning

Create a detailed implementation plan before writing code.

## Instructions

### Input Required
Describe the feature: $ARGUMENTS

### Planning Process

1. **Understand Requirements**
   - What problem does this solve?
   - Does it change Aria's conversation behavior (-> `agent/prompts.py`), add/modify a tool
     (-> `agent/tools.py` + `agent/bot.py`), or touch transport/pipeline/deployment
     (-> `agent/bot.py`, Pipecat Cloud config)?
   - What existing code needs modification?

2. **Research Existing Patterns**
   - Check `agent/prompts.py` for how triage/booking/emergency flows and hard rules are
     currently written
   - Check `agent/tools.py` for the tool-function pattern (docstring `Args:` -> schema,
     `params.result_callback`)
   - Check `agent/bot.py` for pipeline wiring and tool registration
   - Consult `_refs/pipecat/` and `_refs/pipecat-flows/` for framework patterns (use the
     `pipecat-expert` subagent for deep research)

3. **Design Implementation**
   - List files to create/modify
   - Define new/changed tool schemas (docstring `Args:` blocks)
   - Identify external API calls (e.g. Twilio for outbound calling)
   - Consider error handling and demo-vs-production scope (see
     `docs/hvac_voice_agent_demo.md` section 3)

4. **Create Plan Document**
   Save to `.claude/plans/{feature-name}.md`:
   ```markdown
   # Feature: {name}

   ## Summary
   {one-line description}

   ## Files to Modify
   - [ ] file1.py - reason
   - [ ] file2.py - reason

   ## Files to Create
   - [ ] new_file.py - purpose

   ## Implementation Steps
   1. Step one
   2. Step two

   ## Testing Strategy
   - `python tests/run_scenarios.py --scenario {scenario_id}` (or all scenarios)
   - chat_test.py (text-only local test) once available

   ## Risks/Questions
   - Risk or question here
   ```

5. **Get Approval**
   Present plan summary, wait for user approval before executing.

## Usage
```
/plan-feature add an outbound-call tool so Aria can call a lead back via Twilio
```
