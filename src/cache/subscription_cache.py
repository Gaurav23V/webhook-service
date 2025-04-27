import json
from uuid import UUID
from src.queue.redis_conn import redis_conn
from src.db.session import SessionLocal
from src.models.subscription import Subscription
from sqlalchemy.orm import Session

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
    try:
        redis_conn.set(key, json.dumps(data))
    except Exception:
        # Silently ignore caching failures
        pass

def get_subscription(subscription_id: UUID | str, db: Session = None) -> dict | None:
    """
    Return the subscription data dict from Redis if present; otherwise
    load from Postgres, cache it, and return. Returns None if no such
    subscription exists. Cache failures are silently ignored.
    
    Args:
        subscription_id: The UUID of the subscription to get
        db: Optional SQLAlchemy session to use. If None, creates a new one.
    """
    sid = str(subscription_id)
    key = _make_key(sid)

    # 1) Try cache
    try:
        raw = redis_conn.get(key)
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                # corrupted cache entry; fall back to DB
                pass
    except Exception:
        # Redis unavailable or error → cache miss
        pass

    # 2) Cache miss or error → load from DB
    session_created = False
    if db is None:
        db = SessionLocal()
        session_created = True
    
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
        # Try to update cache (best‐effort)
        try:
            redis_conn.set(key, json.dumps(data))
        except Exception:
            pass
        return data
    finally:
        if session_created:
            db.close()

def invalidate_subscription(subscription_id: UUID | str) -> None:
    """
    Remove a subscription’s cache entry (e.g. on delete).
    """
    key = _make_key(str(subscription_id))
    try:
        redis_conn.delete(key)
    except Exception:
        pass
