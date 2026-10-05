from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import get_engine


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    get_settings.cache_clear()
    get_engine.cache_clear()

    from app.main import app

    with TestClient(app) as test_client:  # runs the lifespan (migrations)
        yield test_client

    get_engine().dispose()
    get_settings.cache_clear()
    get_engine.cache_clear()
