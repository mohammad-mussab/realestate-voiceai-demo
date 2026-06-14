# Validate - Run All Checks

Run comprehensive validation on the codebase.

## Instructions

### Validation Steps

1. **Syntax Check**
   ```bash
   cd agent
   python -m py_compile bot.py prompts.py tools.py sms.py
   ```

2. **Import Validation**
   ```bash
   cd agent
   source .venv/bin/activate
   python -c "from tools import check_service_area, check_availability, book_appointment, escalate_emergency, capture_lead, transfer_to_human, send_confirmation_sms; print('OK')"
   python -c "from prompts import SYSTEM_INSTRUCTION; print('OK')"
   ```

3. **Scenario Tests**
   ```bash
   cd agent
   source .venv/bin/activate
   python tests/run_scenarios.py
   ```
   (or `python tests/run_scenarios.py --scenario {id}` for a single scenario)

4. **chat_test.py** (text-only local test) — once available, run as a fast pre-scenario check

5. **Manual Browser Check** (for behavior/pipeline changes)
   - `python bot.py`, open `http://localhost:7860/client`, allow mic
   - Run through a routine booking and an emergency call

6. **Environment Check**
   - Verify `.env` has `GEMINI_API_KEY` set
   - Twilio vars (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`) optional —
     `send_confirmation_sms` logs instead of sending if unset

### Output
Report:
- Syntax: PASS/FAIL
- Imports: PASS/FAIL
- Scenario tests: PASS/FAIL/SKIP (with pass/fail counts)
- Issues found (if any)

## Usage
```
/validate
```
