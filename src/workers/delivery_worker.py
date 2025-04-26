import logging
import os
from datetime import datetime, timedelta
import requests
from sqlalchemy.orm import Session

from src.db.session import SessionLocal
from src.models.delivery_log import DeliveryLog
from src.queue.redis_conn import delivery_queue
from src.cache.subscription_cache import get_subscription

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "5"))
MAX_ATTEMPTS = 5
BACKOFF_SCHEDULE = [10, 30, 60, 300, 900]  # in seconds

def process_delivery(
    subscription_id,
    payload,
    event_type,
    signature,
    webhook_id,
    attempt,
):
    """
    1) Fetch subscription from Redis cache (fallback to DB).
    2) Attempt HTTP POST to target_url.
    3) Log each attempt to Postgres.
    4) If attempt < MAX, reschedule with exponential backoff.
    """
    # Cache-first subscription lookup
    sub_data = get_subscription(subscription_id)
    if not sub_data:
        logger.error(f"[Delivery] Sub {subscription_id} not found, dropping job")
        return

    target = sub_data["target_url"]
    headers = {"Content-Type": "application/json"}
    if event_type:
        headers["X-Event-Type"] = event_type
    if signature:
        headers["X-Signature"] = signature

    db: Session = SessionLocal()
    try:
        status_code = None
        error_details = None
        outcome = None

        # Perform the POST
        try:
            resp = requests.post(
                target,
                json=payload,
                headers=headers,
                timeout=HTTP_TIMEOUT,
            )
            status_code = resp.status_code
            if 200 <= status_code < 300:
                outcome = "Success"
            else:
                outcome = "Failed Attempt"
                error_details = f"HTTP {status_code}"
                raise Exception(error_details)

        except Exception as exc:
            # Recoverable failure: log & re-enqueue if attempts remain
            if attempt < MAX_ATTEMPTS:
                outcome = "Failed Attempt"
                error_details = str(exc)

                # Persist this attempt
                db.add(
                    DeliveryLog(
                        webhook_id=webhook_id,
                        subscription_id=subscription_id,
                        target_url=target,
                        timestamp=datetime.utcnow(),
                        attempt_number=attempt,
                        outcome=outcome,
                        status_code=status_code,
                        error=error_details,
                    )
                )
                db.commit()

                # Schedule next attempt with backoff
                delay = BACKOFF_SCHEDULE[attempt - 1]
                delivery_queue.enqueue_in(
                    timedelta(seconds=delay),
                    process_delivery,
                    subscription_id,
                    payload,
                    event_type,
                    signature,
                    webhook_id,
                    attempt + 1,
                )
                return
            # else fall through to final failure

        # Final log (either success or last failure)
        if outcome is None:
            outcome = "Success"
        db.add(
            DeliveryLog(
                webhook_id=webhook_id,
                subscription_id=subscription_id,
                target_url=target,
                timestamp=datetime.utcnow(),
                attempt_number=attempt,
                outcome=outcome,
                status_code=status_code,
                error=error_details,
            )
        )
        db.commit()

    finally:
        db.close()
