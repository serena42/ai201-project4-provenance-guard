import json
import os
from datetime import datetime, timezone

STORE_PATH = os.path.join(os.path.dirname(__file__), "verified_creators.json")

VERIFICATION_CONFIDENCE_THRESHOLD = 0.80
VERIFICATION_MIN_WORD_COUNT = 30

CERTIFICATE_LABEL = (
    "✓ Verified Human Creator: this creator completed a live-writing "
    "identity check and their account is marked as a verified human author. "
    "Individual submissions are still scored on their own merits above."
)


def _read_all():
    if not os.path.exists(STORE_PATH):
        return {}
    with open(STORE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_all(records):
    with open(STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)


def get_verification(creator_id):
    return _read_all().get(creator_id)


def is_verified(creator_id):
    return get_verification(creator_id) is not None


def mark_verified(creator_id, confidence, word_count):
    records = _read_all()
    record = {
        "creator_id": creator_id,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "verification_confidence": confidence,
        "verification_word_count": word_count,
    }
    records[creator_id] = record
    _write_all(records)
    return record
