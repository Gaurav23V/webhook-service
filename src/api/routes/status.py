from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from uuid import UUID
from typing import List

from src.db.session import SessionLocal
from src.models.delivery_log import DeliveryLog
from src.api.schemas import DeliveryAttempt, StatusResponse

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get(
    "/status/{webhook_id}",
    response_model=StatusResponse,
    summary="Get delivery status and recent attempts for a webhook",
)
def get_webhook_status(
    webhook_id: UUID,
    db: Session = Depends(get_db),
):
    # 1) total count
    total = db.query(func.count(DeliveryLog.id)) \
              .filter(DeliveryLog.webhook_id == webhook_id) \
              .scalar()
    if total == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No delivery logs for given webhook_id",
        )

    # 2) recent attempts (most recent first, up to 20)
    logs = (
        db.query(DeliveryLog)
          .filter(DeliveryLog.webhook_id == webhook_id)
          .order_by(DeliveryLog.timestamp.desc())
          .limit(20)
          .all()
    )

    last = logs[0]
    return {
        "webhook_id": webhook_id,
        "subscription_id": last.subscription_id,
        "total_attempts": total,
        "final_outcome": last.outcome,
        "last_attempt_at": last.timestamp,
        "last_status_code": last.status_code,
        "error": last.error,
        "recent_attempts": logs,
    }

@router.get(
    "/subscriptions/{subscription_id}/attempts",
    response_model=List[DeliveryAttempt],
    summary="List recent delivery attempts for a subscription",
)
def list_subscription_attempts(
    subscription_id: UUID,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    logs = (
        db.query(DeliveryLog)
          .filter(DeliveryLog.subscription_id == subscription_id)
          .order_by(DeliveryLog.timestamp.desc())
          .limit(limit)
          .all()
    )
    return logs
