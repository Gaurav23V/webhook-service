import os
import pytest
import redis
from rq import Queue

# Decide whether to spin up testcontainers or trust env vars (CI)
USE_TESTCONTAINERS = "CI" not in os.environ

if USE_TESTCONTAINERS:
    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session")
def postgres_container():
    """Starts the Postgres container if using testcontainers."""
    if not USE_TESTCONTAINERS:
        yield None
        return
    pg = PostgresContainer("postgres:14-alpine")
    pg.start()
    yield pg
    pg.stop()

@pytest.fixture(scope="session")
def redis_container():
    """Starts the Redis container if using testcontainers."""
    if not USE_TESTCONTAINERS:
        yield None
        return
    rr = RedisContainer("redis:6-alpine")
    rr.start()
    yield rr
    rr.stop()


@pytest.fixture(scope="session", autouse=True)
def set_environment_urls(postgres_container, redis_container):
    """
    Sets DATABASE_URL and REDIS_URL environment variables based on
    containers (if used) or assumes they exist (CI).
    Runs automatically for the session AFTER containers are started.
    """
    if postgres_container:
        os.environ["DATABASE_URL"] = postgres_container.get_connection_url()
    if redis_container:
        host = redis_container.get_container_host_ip()
        port = redis_container.get_exposed_port(6379)
        os.environ["REDIS_URL"] = f"redis://{host}:{port}/0"


@pytest.fixture(scope="session")
def db_engine(set_environment_urls): # Depend on env vars being set
    """Creates the DB engine and tables."""
    # Import here ensures it uses the env var set by set_environment_urls
    from src.db.session import engine, Base
    # Import models here to ensure they are registered with the Base
    # before create_all is called. This is crucial.
    from src.models.subscription import Subscription
    from src.models.delivery_log import DeliveryLog

    Base.metadata.create_all(bind=engine)
    yield engine
    # Optional: Drop tables at the end if needed
    # Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session")
def test_redis_conn(redis_container): # Depend on the container fixture
    """Creates a Redis connection using the running test container or env URL."""
    if redis_container:
        host = redis_container.get_container_host_ip()
        port = redis_container.get_exposed_port(6379)
        redis_url = f"redis://{host}:{port}/0"
    else:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    conn = redis.from_url(redis_url)
    try:
        conn.ping()
    except redis.exceptions.ConnectionError as e:
        pytest.fail(f"Redis connection failed: {e}") # Fail fast if Redis isn't up
    conn.flushall()
    return conn


@pytest.fixture(scope="session")
def test_delivery_queue(test_redis_conn):
    """Creates an RQ Queue using the test Redis connection."""
    queue = Queue("deliveries", connection=test_redis_conn)
    return queue


@pytest.fixture(scope="session", autouse=True)
def patch_redis_module(test_redis_conn, test_delivery_queue):
    """
    Patch both the queue module *and* the subscription_cache module
    so that all code uses the test Redis connection/queue.
    """
    # patch src.queue.redis_conn
    from src.queue import redis_conn as queue_module
    orig_queue_conn = queue_module.redis_conn
    orig_queue_queue = queue_module.delivery_queue
    queue_module.redis_conn = test_redis_conn
    queue_module.delivery_queue = test_delivery_queue

    # patch src.cache.subscription_cache
    from src.cache import subscription_cache as cache_module
    orig_cache_conn = cache_module.redis_conn
    cache_module.redis_conn = test_redis_conn

    yield

    # restore
    queue_module.redis_conn = orig_queue_conn
    queue_module.delivery_queue = orig_queue_queue
    cache_module.redis_conn = orig_cache_conn



@pytest.fixture(scope="function")
def db_session(db_engine):
    """Provides a transactional session for tests."""
    # Import SessionLocal here to ensure it uses the correct engine
    from src.db.session import SessionLocal
    from sqlalchemy.orm import sessionmaker

    connection = db_engine.connect()
    transaction = connection.begin()
    # Use sessionmaker configured with the correct engine via SessionLocal
    # Or re-create sessionmaker if SessionLocal itself needs rebinding
    TestingSessionLocal = sessionmaker(bind=connection)
    session = TestingSessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def redis_conn():
    """Provides the session-patched redis connection."""
    from src.queue.redis_conn import redis_conn
    return redis_conn


@pytest.fixture(scope="function")
def delivery_queue():
    """Provides the session-patched delivery queue."""
    from src.queue.redis_conn import delivery_queue
    delivery_queue.empty()
    return delivery_queue


@pytest.fixture(scope="function")
def client(db_session): # Depends on db_session -> db_engine -> set_env -> containers
    """Provides a FastAPI TestClient with DB dependency override."""
    # Import app and get_db functions here, after engine/session might be configured
    from fastapi.testclient import TestClient
    from src.api.main import app
    from src.api.routes.subscriptions import get_db as subs_get_db
    from src.api.routes.status import get_db as status_get_db

    def override_get_db():
        try:
            yield db_session
        finally:
            pass # Session managed by db_session fixture

    app.dependency_overrides[subs_get_db] = override_get_db
    app.dependency_overrides[status_get_db] = override_get_db

    yield TestClient(app)

    app.dependency_overrides = {} # Clean up overrides

