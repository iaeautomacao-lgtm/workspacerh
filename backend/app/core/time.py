from datetime import datetime, timezone

def utcnow():
    """Naive UTC for portable SQL DATETIME storage; APIs annotate UTC when serialized."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
