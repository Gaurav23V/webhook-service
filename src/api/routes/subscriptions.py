from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from src.db.session import SessionLocal
from src.models.subscription import Subscription
from src.api.schemas import (
    SubscriptionCreate,
    SubscriptionOut,
    SubscriptionUpdate,
)

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post(
    "/",
    response_model=SubscriptionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_subscription(
    subscription_in: SubscriptionCreate,
    db: Session = Depends(get_db),
):
    sub = Subscription(**subscription_in.dict())
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub

@router.get("/{subscription_id}", response_model=SubscriptionOut)
def read_subscription(
    subscription_id: UUID,
    db: Session = Depends(get_db),
):
    sub = db.query(Subscription).get(subscription_id)
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
    return sub

@router.get("/", response_model=List[SubscriptionOut])
def list_subscriptions(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return db.query(Subscription).offset(skip).limit(limit).all()

@router.patch("/{subscription_id}", response_model=SubscriptionOut)
def update_subscription(
    subscription_id: UUID,
    subscription_in: SubscriptionUpdate,
    db: Session = Depends(get_db),
):
    sub = db.query(Subscription).get(subscription_id)
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
    update_data = subscription_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(sub, field, value)
    db.commit()
    db.refresh(sub)
    return sub

@router.delete(
    "/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_subscription(
    subscription_id: UUID,
    db: Session = Depends(get_db),
):
    sub = db.query(Subscription).get(subscription_id)
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
    db.delete(sub)
    db.commit()
    return
