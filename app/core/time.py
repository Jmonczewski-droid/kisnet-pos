from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC timestamp for storage."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
