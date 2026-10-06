"""Test fixtures: force a throwaway SQLite database before any app import."""
import os
import tempfile

_DB_FD, _DB_PATH = tempfile.mkstemp(prefix="hallspan_test_", suffix=".db")
os.close(_DB_FD)
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ["SEED_ON_EMPTY"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.seed import seed_if_empty  # noqa: E402


@pytest.fixture()
def client():
    # Fresh schema for every test.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()
    with TestClient(app) as c:
        yield c
