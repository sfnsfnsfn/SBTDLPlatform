from datetime import datetime, timezone


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp string for SQLite storage."""
    return datetime.now(timezone.utc).isoformat()
