import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session # Import Session
from src.db.session import SessionLocal
from src.models.delivery_log import DeliveryLog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def purge_old_logs(db: Session | None = None):
    """
    Delete delivery logs older than 72 hours.
    Run this once an hour (via cron, RQ scheduler, or docker-compose cron service).

    Args:
        db: Optional SQLAlchemy session to use. If None, creates a new one.
    """
    session_created = False
    if db is None:
        db = SessionLocal()
        session_created = True

    try:
        cutoff = datetime.utcnow() - timedelta(hours=72)
        # Use the provided or newly created session 'db'
        deleted = db.query(DeliveryLog) \
                    .filter(DeliveryLog.timestamp < cutoff) \
                    .delete(synchronize_session=False)

        # Only commit if we created the session within this function
        if session_created:
            db.commit()

        logger.info(f"Purged {deleted} delivery log(s) before {cutoff.isoformat()}")
    except Exception:
        # Rollback if we created the session and an error occurred
        if session_created:
            db.rollback()
        logger.exception("Error during log purge.")
        raise # Re-raise the exception
    finally:
        # Only close if we created the session within this function
        if session_created:
            db.close()