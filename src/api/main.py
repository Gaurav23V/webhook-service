from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.db.session import Base, engine
from src.api.routes.subscriptions import router as subs_router
from src.api.routes.ingest import router as ingest_router
from src.api.routes.status import router as status_router
from src.models.subscription import Subscription
from src.models.delivery_log import DeliveryLog

# Auto-create all tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Webhook Delivery Service",
    version="0.1.0",
    openapi_url="/openapi.json",
    docs_url="/docs",
)

origins = [
    "http://localhost:5173", # Vite default dev server
    "http://localhost:3000", # Create React App default
    # Add your deployed frontend URL here later
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Allow all methods (GET, POST, PATCH, DELETE, etc.)
    allow_headers=["*"], # Allow all headers
)

# Subscription CRUD
app.include_router(
    subs_router,
    prefix="/subscriptions",
    tags=["subscriptions"],
)

# Ingestion endpoint
app.include_router(
    ingest_router,
    tags=["ingest"],
)

# Status & Analytics endpoints
app.include_router(
    status_router,
    tags=["analytics"],
)