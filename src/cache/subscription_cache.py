import json
from uuid import UUID
from src.queue.redis_conn import redis_conn
from src.db.session import SessionLocal
from src.models.subscription import Subscription

CACHE_PREFIX = "subscription:"

def _make_key(subscription_id: str) -> str:
    return f"{CACHE_PREFIX}{subscription_id}"

def cache_subscription(sub: Subscription) -> None:
    """
    Store the subscription’s core fields in Redis under a JSON string.
    """
    key = _make_key(str(sub.id))
    data = {
        "id": str(sub.id),
        "target_url": sub.target_url,
        "secret": sub.secret,
        "events": sub.events or [],
    }
    redis_conn.set(key, json.dumps(data))

def get_subscription(subscription_id: UUID | str) -> dict | None:
    """
    Return the subscription data dict from Redis if present; otherwise
    load from Postgres, cache it, and return. Returns None if no such
    subscription exists.
    """
    sid = str(subscription_id)
    key = _make_key(sid)

    raw = redis_conn.get(key)
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass  # fall back to DB

    # Cache miss → load from DB
    db = SessionLocal()
    try:
        sub = db.query(Subscription).get(sid)
        if not sub:
            return None
        data = {
            "id": str(sub.id),
            "target_url": sub.target_url,
            "secret": sub.secret,
            "events": sub.events or [],
        }
        redis_conn.set(key, json.dumps(data))
        return data
    finally:
        db.close()

def invalidate_subscription(subscription_id: UUID | str) -> None:
    """
    Remove a subscription’s cache entry (e.g. on delete).
    """
    key = _make_key(str(subscription_id))
    redis_conn.delete(key)
