"""Quick manual test: insert a sample call summary via db.log_call().

Run with:
    python test_db.py

Then check the call_logs table in Supabase for a new row.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(override=True)

from db import log_call

sample_summary = {
    "lead_name": "Test Lead",
    "lead_phone": "+15555550123",
    "lead_type": "buyer",
    "timeline": "1-3 months",
    "area": "Austin",
    "price_range": "$800,000 - $900,000",
    "pre_approved": False,
    "property_needs": "6 bed, 6 bath, lawn, garage for 2 cars",
    "seller_address": "",
    "appointment_type": "call_back",
    "appointment_time": "within the hour",
    "booking_id": "SRG-TEST",
    "hot_lead": False,
    "notes": "Test row from test_db.py",
}

result = log_call(sample_summary)
print(result)
