import logging
import os
from sqlalchemy.orm import Session
import requests

from src.db.session import SessionLocal
from src.models.subscription import Subscription

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# HTTP timeout in seconds (env var or default 5s)
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "5"))

def process_delivery(subscription_id, payload, event_type=None):
    """
    Consume a delivery job: lookup subscription, POST payload to its target_url,
    apply a timeout, and log success or failure. On failure we raise to
    trigger RQ’s retry mechanism in the next phase.
    """
    db: Session = SessionLocal()
    try:
        # 1. Fetch subscription; if missing, drop the job
        sub = db.query(Subscription).get(subscription_id)
        if not sub:
            logger.error(f"[Delivery] Sub {subscription_id} not found, dropping job")
            return

        # 2. Build headers
        headers = {"Content-Type": "application/json"}
        if event_type:
            headers["X-Event-Type"] = event_type

        # 3. Send the POST
        response = requests.post(
            sub.target_url,
            json=payload,
            headers=headers,
            timeout=HTTP_TIMEOUT,
        )

        # 4. Handle response
        if 200 <= response.status_code < 300:
            logger.info(
                f"[Delivery] Success {subscription_id} → {sub.target_url} "
                f"(status={response.status_code})"
            )
        else:
            msg = (
                f"[Delivery] Failed {subscription_id} → {sub.target_url} "
                f"(status={response.status_code})"
            )
            logger.error(msg)
            # Raise to let RQ retry
            raise Exception(msg)

    except Exception as exc:
        logger.exception(f"[Delivery] Exception for sub {subscription_id}: {exc}")
        # RQ will catch this and retry according to its policy
        raise
    finally:
        db.close()
