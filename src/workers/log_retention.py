import logging
from datetime import datetime, timedelta
from src.db.session import SessionLocal
from src.models.delivery_log import DeliveryLog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def purge_old_logs():
    """
    Delete delivery logs older than 72 hours.
    Run this once an hour (via cron, RQ scheduler, or docker-compose cron service).
    """
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(hours=72)
        deleted = db.query(DeliveryLog) \
                    .filter(DeliveryLog.timestamp < cutoff) \
                    .delete(synchronize_session=False)
        db.commit()
        logger.info(f"Purged {deleted} delivery log(s) before {cutoff.isoformat()}")
    finally:
        db.close()
