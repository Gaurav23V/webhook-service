from datetime import datetime, timedelta
import uuid

from src.models.delivery_log import DeliveryLog
from src.workers.log_retention import purge_old_logs

def test_purge_old_logs(db_session):
    # Insert one old and one recent log
    old_id = uuid.uuid4()  # Save IDs for later queries
    new_id = uuid.uuid4()
    
    old = DeliveryLog(
        id=old_id,  # Explicitly set ID
        webhook_id=uuid.uuid4(),
        subscription_id=uuid.uuid4(),
        target_url="http://old",
        timestamp=datetime.utcnow() - timedelta(hours=73),
        attempt_number=1,
        outcome="Failed"
    )
    new = DeliveryLog(
        id=new_id,  # Explicitly set ID
        webhook_id=uuid.uuid4(),
        subscription_id=uuid.uuid4(),
        target_url="http://new",
        timestamp=datetime.utcnow() - timedelta(hours=1),
        attempt_number=1,
        outcome="Success"
    )
    db_session.add_all([old, new])
    db_session.flush()

    # Purge using the *same* session/transaction
    purge_old_logs(db=db_session)

    # Query only for the specific logs we created
    old_exists = db_session.query(DeliveryLog).filter_by(id=old_id).first() is not None
    new_exists = db_session.query(DeliveryLog).filter_by(id=new_id).first() is not None

    # Assert that only the new log remains
    assert not old_exists, "Old log should have been deleted"
    assert new_exists, "New log should still exist"