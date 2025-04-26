import logging
import os
from datetime import datetime, timedelta
import requests
from sqlalchemy.orm import Session

from src.db.session import SessionLocal
from src.models.subscription import Subscription
from src.models.delivery_log import DeliveryLog
from src.queue.redis_conn import delivery_queue

# configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# config & backoff
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
    1) Attempt to POST to the subscription target_url.
    2) On success or final failure, record a DeliveryLog row.
    3) On intermediate failure (attempt < MAX_ATTEMPTS), record the failure,
       schedule the next attempt after BACKOFF_SCHEDULE[attempt-1] seconds.
    """
    db: Session = SessionLocal()
    try:
        sub = db.query(Subscription).get(subscription_id)
        if not sub:
            logger.error(
                f"Subscription {subscription_id} not found, dropping job")
            return

        target = sub.target_url
        headers = {"Content-Type": "application/json"}
        if event_type:
            headers["X-Event-Type"] = event_type
        if signature:
            headers["X-Signature"] = signature

        status_code = None
        error_details = None
        outcome = None

        # perform the POST
        try:
            resp = requests.post(
                target,
                json=payload,
                headers=headers,
                timeout=HTTP_TIMEOUT,
            )
            status_code = resp.status_code
            if 200 <= resp.status_code < 300:
                outcome = "Success"
            else:
                outcome = "Failed Attempt"
                error_details = f"HTTP {resp.status_code}"
                raise Exception(error_details)

        except Exception as exc:
            # if we can retry, record a failed-attempt log & re-enqueue
            if attempt < MAX_ATTEMPTS:
                outcome = "Failed Attempt"
                error_details = str(exc)

                # persist this attempt
                log = DeliveryLog(
                    webhook_id=webhook_id,
                    subscription_id=subscription_id,
                    target_url=target,
                    timestamp=datetime.utcnow(),
                    attempt_number=attempt,
                    outcome=outcome,
                    status_code=status_code,
                    error=error_details,
                )
                db.add(log)
                db.commit()

                # schedule the next attempt
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

        # record final log (either success or final failure)
        if outcome is None:
            # This branch only if the inner try never set outcome (shouldn't happen)
            outcome = "Success"
        log = DeliveryLog(
            webhook_id=webhook_id,
            subscription_id=subscription_id,
            target_url=target,
            timestamp=datetime.utcnow(),
            attempt_number=attempt,
            outcome=outcome if outcome else "Failure",
            status_code=status_code,
            error=error_details,
        )
        db.add(log)
        db.commit()

    finally:
        db.close()
