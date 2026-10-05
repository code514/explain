from pathlib import Path

from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parent.parent


def alembic_config(database_url: str | None = None) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    if database_url:
        cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return cfg


def run_migrations(database_url: str | None = None) -> None:
    cfg = alembic_config(database_url)
    # Keep Alembic from reconfiguring logging (it would silence uvicorn's loggers).
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
