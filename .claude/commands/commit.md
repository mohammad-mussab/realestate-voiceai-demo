# Commit - Git Commit with Conventional Format

Create a well-formatted git commit.

## Instructions

### Optional Input
Commit message override: $ARGUMENTS

### Process

1. **Check Status**
   ```bash
   git status
   git diff --staged
   ```

2. **Analyze Changes**
   - What type of change? (feat/fix/refactor/docs/chore/test)
   - What's the scope? (prompt, tools, bot, sms, tests, docs)
   - Why was this change made?

3. **Format Commit Message**
   Use conventional commits:
   ```
   <type>(<scope>): <description>

   <body if needed>
   ```

   Types:
   - `feat`: New feature
   - `fix`: Bug fix
   - `refactor`: Code change that neither fixes a bug nor adds a feature
   - `docs`: Documentation only
   - `chore`: Maintenance tasks
   - `test`: Adding/updating scenario tests

   Scopes (for this project):
   - `prompt`: `SYSTEM_INSTRUCTION` / Aria persona, triage, flow changes (`agent/prompts.py`)
   - `tools`: Tool functions/schemas (`agent/tools.py`)
   - `bot`: Pipeline wiring, transport, tool registration (`agent/bot.py`)
   - `sms`: Twilio SMS helper (`agent/sms.py`)
   - `tests`: Scenario tests (`agent/tests/`)
   - `docs`: Documentation (`README.md`, `docs/`, `.claude/`)

4. **Stage and Commit**
   ```bash
   git add <files>
   git commit -m "<message>"
   ```

### Examples
```
feat(prompt): add price hard rule for new system quotes
fix(tools): correct booking_id format in book_appointment
test(tests): add scenario for out-of-area caller
```

## Usage
```
/commit
/commit feat(prompt): tighten emergency triage for gas smell
```

Note: Does NOT push. Run `git push` manually when ready.
