"""Test fixtures: PostgreSQL via testcontainers + FastAPI TestClient."""

# Import models before app to (a) register them in Base.metadata for create_all
# and (b) avoid shadowing the `app` FastAPI instance with the `app` package name.
import app.models.bill  # noqa: F401
import app.models.category  # noqa: F401
import app.models.payment  # noqa: F401
import app.models.reset_token  # noqa: F401
import app.models.restore_snapshot  # noqa: F401
import app.models.user  # noqa: F401

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer

from app.core.database import Base, get_db
from app.main import app

# Raise per-scope rate limits to an effectively unbounded value so the suite's
# shared 127.0.0.1 (and per-user) buckets never trip 429. Limits are read at
# request time, so mutating the settings singleton here is sufficient.
from app.core.config import settings as _settings

for _scope in (
    "login",
    "register",
    "forgot_password",
    "reset_password",
    "change_password",
    "change_email",
    "send_now",
):
    setattr(_settings, f"{_scope}_rate_limit", 100000)


@pytest.fixture(scope="session")
def postgres_engine():
    with PostgresContainer("postgres:17") as pg:
        engine = create_engine(pg.get_connection_url(), poolclass=NullPool)
        yield engine


@pytest.fixture()
def db_tables(postgres_engine):
    Base.metadata.create_all(bind=postgres_engine)
    yield
    Base.metadata.drop_all(bind=postgres_engine)


@pytest.fixture()
def db_session(postgres_engine, db_tables):
    Session = sessionmaker(bind=postgres_engine, autocommit=False, autoflush=False)
    db = Session()
    yield db
    db.close()


@pytest.fixture()
def db_sessionmaker(postgres_engine, db_tables):
    return sessionmaker(bind=postgres_engine, autocommit=False, autoflush=False)


@pytest.fixture()
def client(postgres_engine):
    Base.metadata.create_all(bind=postgres_engine)
    _SessionLocal = sessionmaker(
        bind=postgres_engine, autocommit=False, autoflush=False
    )

    def _override_get_db():
        db = _SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=postgres_engine)


@pytest.fixture()
def client_db(postgres_engine):
    """TestClient + direct DB session sharing the same engine."""
    Base.metadata.create_all(bind=postgres_engine)
    SessionLocal = sessionmaker(bind=postgres_engine, autocommit=False, autoflush=False)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        db = SessionLocal()
        yield c, db
        db.close()
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=postgres_engine)


def register_and_login(
    client: TestClient, email: str, password: str = "pw123456"
) -> str:
    """Register a user and return their Bearer token."""
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def sync_payments(client: TestClient, token: str, month: str | None = None) -> None:
    """Seed payment instances for the current month (or a given month), then return."""
    from datetime import date as _date

    target = month or _date.today().strftime("%Y-%m")
    r = client.post(f"/bills/sync-instances?month={target}", headers=auth(token))
    assert r.status_code == 204, r.text
