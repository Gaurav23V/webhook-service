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
from src.cache.subscription_cache import cache_subscription, invalidate_subscription

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
    # Convert Pydantic model to dict
    sub_data = subscription_in.dict()

    # Convert AnyHttpUrl to string before creating SQLAlchemy model 
    if sub_data.get("target_url"):
        sub_data["target_url"] = str(sub_data["target_url"])

    # Create SQLAlchemy model instance
    sub = Subscription(**sub_data)

    db.add(sub)
    db.commit()
    db.refresh(sub)

    # Cache the new subscription
    cache_subscription(sub)

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

    # Get update data, excluding unset fields
    update_data = subscription_in.dict(exclude_unset=True)

    for field, value in update_data.items():
        # Convert AnyHttpUrl to string if target_url is being updated
        if field == "target_url" and value is not None:
            setattr(sub, field, str(value))
        else:
            setattr(sub, field, value) # Set other fields normally

    db.commit()
    db.refresh(sub)

    # Update cache
    cache_subscription(sub)

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

    # Invalidate cache
    invalidate_subscription(subscription_id)

    # No return needed for 204
    return