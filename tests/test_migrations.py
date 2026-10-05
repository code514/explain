from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, inspect

from app.migrations import alembic_config, run_migrations


def test_upgrade_head_on_empty_db(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'migrate.db'}"
    run_migrations(url)
    tables = inspect(create_engine(url)).get_table_names()
    assert set(tables) == {"alembic_version", "tickers", "prices"}


def test_models_match_migrations(tmp_path: Path) -> None:
    """Equivalent of `alembic check`: no drift between models and migrations."""
    url = f"sqlite:///{tmp_path / 'check.db'}"
    run_migrations(url)
    command.check(alembic_config(url))
