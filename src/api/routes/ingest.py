import os
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, status
from starlette.requests import Request
from starlette.responses import Response
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
    # 1. Verify subscription exists
    sub = db.query(Subscription).get(subscription_id)
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    # 2. Parse JSON payload
    payload = await request.json()

    # 3. Enqueue the delivery job (subscription_id, payload, event type)
    delivery_queue.enqueue(
        "src.workers.delivery_worker.process_delivery",
        subscription_id,
        payload,
        x_event_type,
        retry=True,
    )

    # 4. Acknowledge immediately
    return Response(status_code=status.HTTP_202_ACCEPTED)
