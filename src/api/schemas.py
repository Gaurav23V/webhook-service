from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, AnyHttpUrl

class SubscriptionBase(BaseModel):
    target_url: AnyHttpUrl
    secret: Optional[str] = None
    events: Optional[List[str]] = None

class SubscriptionCreate(SubscriptionBase):
    pass

class SubscriptionUpdate(BaseModel):
    target_url: Optional[AnyHttpUrl] = None
    secret: Optional[str] = None
    events: Optional[List[str]] = None

class SubscriptionOut(SubscriptionBase):
    id: UUID

    class Config:
        orm_mode = True
