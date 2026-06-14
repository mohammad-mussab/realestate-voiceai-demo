"""Quick manual test: send a real SMS via sms.send_sms().

Run with:
    python test_sms.py +1XXXXXXXXXX

Requires TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER in .env.
On a Twilio trial account, the "to" number must be a Verified Caller ID.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(override=True)

from sms import send_sms

to_number = sys.argv[1] if len(sys.argv) > 1 else ""
if not to_number:
    print("Usage: python test_sms.py +1XXXXXXXXXX")
    sys.exit(1)

result = send_sms(
    to=to_number,
    body="Hi from Summit Realty Group! This is a test confirmation from Ava.",
)
print(result)
