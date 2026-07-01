import json
import os
from datetime import datetime, timezone

LOG_PATH = os.path.join(os.path.dirname(__file__), "audit_log.json")


def _read_all():
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def append_entry(entry):
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(), **entry}
    entries = _read_all()
    entries.append(entry)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)
    return entry


def get_entries(limit=50):
    entries = _read_all()
    return list(reversed(entries))[:limit]


def get_latest_entry_by_content_id(content_id):
    matches = [e for e in _read_all() if e.get("content_id") == content_id]
    return matches[-1] if matches else None


def get_all_entries():
    return _read_all()
