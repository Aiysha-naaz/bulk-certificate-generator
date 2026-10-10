import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["CERT_OUTPUT_DIR"] = f"{_tmp}/out"




@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    return TestClient(app)