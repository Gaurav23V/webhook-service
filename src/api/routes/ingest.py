import uuid
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, status
from starlette.requests import Request
from starlette.responses import JSONResponse
from sqlalchemy.orm import Session

from src.db.session import SessionLocal
from src.models.subscription import Subscription
from src.queue.redis_conn import delivery_queue

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post(
    "/ingest/{subscription_id}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a webhook and enqueue for delivery",
)
async def ingest_webhook(
    subscription_id: UUID,
    request: Request,
    x_event_type: str | None = Header(None),
    x_signature: str | None = Header(None),
    db: Session = Depends(get_db),
):
    # 1) verify subscription
    sub = db.query(Subscription).get(subscription_id)
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    # 2) read payload
    payload = await request.json()

    # 3) generate a webhook-level ID and initial attempt=1
    webhook_id = uuid.uuid4()

    # 4) enqueue the first delivery attempt (no built-in RQ retry here)
    delivery_queue.enqueue(
        "src.workers.delivery_worker.process_delivery",
        subscription_id,
        payload,
        x_event_type,
        x_signature,
        webhook_id,
        1,  # first attempt
    )

    # 5) return the webhook_id so clients can query status
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"webhook_id": str(webhook_id)},
    )
