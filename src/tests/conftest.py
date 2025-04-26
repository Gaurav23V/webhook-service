import os
import pytest

# Decide whether to spin up testcontainers or trust env vars (CI)
USE_TESTCONTAINERS = "CI" not in os.environ

if USE_TESTCONTAINERS:
    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer

@pytest.fixture(scope="session", autouse=True)
def test_environment():
    """
    If running locally (no CI env), start Postgres & Redis containers and
    set DATABASE_URL / REDIS_URL. Otherwise assume CI services are available.
    """
    if USE_TESTCONTAINERS:
        pg = PostgresContainer("postgres:14-alpine")
        pg.start()
        os.environ["DATABASE_URL"] = pg.get_connection_url()

        rr = RedisContainer("redis:6-alpine")
        rr.start()
        host = rr.get_container_host_ip()
        port = rr.get_exposed_port(6379)
        os.environ["REDIS_URL"] = f"redis://{host}:{port}/0"

        yield

        pg.stop()
        rr.stop()
    else:
        # CI provides DATABASE_URL & REDIS_URL via workflow env
        yield

@pytest.fixture(scope="session")
def db_engine():
    from src.db.session import engine, Base
    # create all tables
    Base.metadata.create_all(bind=engine)
    return engine

@pytest.fixture(scope="function")
def db_session(db_engine):
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()
    yield session
    session.close()
    # clean up all tables
    from src.db.session import Base
    for tbl in reversed(Base.metadata.sorted_tables):
        db_engine.execute(tbl.delete())

@pytest.fixture(scope="session")
def redis_conn():
    from src.queue.redis_conn import redis_conn
    redis_conn.flushall()
    return redis_conn

@pytest.fixture(scope="function")
def delivery_queue(redis_conn):
    from src.queue.redis_conn import delivery_queue
    delivery_queue.empty()
    return delivery_queue

@pytest.fixture(scope="function")
def client():
    from fastapi.testclient import TestClient
    from src.api.main import app
    return TestClient(app)