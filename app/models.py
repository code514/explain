import datetime as dt

from sqlmodel import Field, SQLModel

# Constraint naming convention. SQLite batch migrations need named constraints
# to drop or alter them later.
SQLModel.metadata.naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


# SQLModel tables (table=True) are defined below.
class Ticker(SQLModel, table=True):
    """Cached company metadata (yfinance `Ticker.info`)."""

    __tablename__ = "tickers"  # type: ignore[assignment]

    symbol: str = Field(primary_key=True)
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    info_fetched_at: dt.datetime


class Price(SQLModel, table=True):
    """One adjusted daily OHLCV bar. All values are null on days without trading."""

    __tablename__ = "prices"  # type: ignore[assignment]

    ticker: str = Field(primary_key=True)
    date: dt.date = Field(primary_key=True)
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: int | None = None
