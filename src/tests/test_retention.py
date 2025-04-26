from datetime import datetime, timedelta
import uuid

import pytest
from src.models.delivery_log import DeliveryLog
from src.workers.log_retention import purge_old_logs

def test_purge_old_logs(db_session):
    # Insert one old and one recent log
    old = DeliveryLog(
        webhook_id=uuid.uuid4(),
        subscription_id=uuid.uuid4(),
        target_url="http://old",
        timestamp=datetime.utcnow() - timedelta(hours=73),
        attempt_number=1,
        outcome="Failed"
    )
    new = DeliveryLog(
        webhook_id=uuid.uuid4(),
        subscription_id=uuid.uuid4(),
        target_url="http://new",
        timestamp=datetime.utcnow() - timedelta(hours=1),
        attempt_number=1,
        outcome="Success"
    )
    db_session.add_all([old, new])
    db_session.commit()

    # Purge
    purge_old_logs()

    # Ensure only the new one remains
    db_session.expire_all()
    remaining = db_session.query(DeliveryLog).all()
    assert len(remaining) == 1
    assert remaining[0].target_url == "http://new"
