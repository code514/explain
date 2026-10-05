"""All SQLite reads and writes. Controllers check here before calling an external adapter.

Each function opens its own short-lived session, so callers never handle the DB.
"""

import datetime as dt

import pandas as pd
from sqlmodel import Session, col, select

from app.db import get_engine
from app.models import Price, Ticker
from app.schemas import TickerInfo
from app.services.yfinance import HISTORY_COLUMNS

PRICE_COLUMNS = [*HISTORY_COLUMNS, "daily_return"]


def get_ticker_info(symbol: str) -> TickerInfo | None:
    """Cached company metadata, or None if it was never saved."""
    with Session(get_engine()) as session:
        row = session.get(Ticker, symbol)
    if row is None:
        return None
    return TickerInfo(symbol=row.symbol, name=row.name, sector=row.sector, industry=row.industry)


def save_ticker_info(info: TickerInfo, now: dt.datetime) -> None:
    """Insert or overwrite the metadata for `info.symbol`. `now` is a timezone-aware fetch time."""
    with Session(get_engine()) as session:
        session.merge(Ticker(**info.model_dump(), info_fetched_at=now))
        session.commit()


def get_ticker_history(symbol: str, start: dt.date, end: dt.date) -> pd.DataFrame | None:
    """Cached daily prices from `start` to `end` inclusive, shaped like `yf_service.get_history`
    plus a `daily_return` column.

    Like Yahoo's, the frame holds trading days only: the null rows stored for weekends and
    holidays are dropped. It can be empty on a hit, e.g. for a range with no trading days.

    Cache hit detection is rudimentary: it is a hit when both `start` and `end` have a
    stored row, and then every day between them is assumed stored too. That holds because
    `save_ticker_history` expects a contiguous range (days without trading saved as nulls).
    Otherwise None.
    """
    with Session(get_engine()) as session:
        if session.get(Price, (symbol, start)) is None or session.get(Price, (symbol, end)) is None:
            return None
        rows = session.exec(
            select(Price)
            .where(Price.ticker == symbol, col(Price.date) >= start, col(Price.date) <= end)
            .order_by(col(Price.date))
        ).all()
    history = pd.DataFrame(
        {column: [getattr(row, column) for row in rows] for column in PRICE_COLUMNS},
        index=pd.DatetimeIndex([row.date for row in rows], name="date").astype("datetime64[ns]"),
    )
    return history.dropna(how="all")  # back to Yahoo's shape: trading days only


def save_ticker_history(symbol: str, history: pd.DataFrame) -> None:
    """Insert or overwrite one row per day of `history`, which needs a `daily_return` column and
    should be contiguous.

    Null values are stored as nulls. Gaps in `history` would later be returned as cache hits
    with missing days, so callers fill them first.
    """
    bars = history.reset_index().to_dict("records")
    with Session(get_engine()) as session:
        for bar in bars:
            session.merge(
                Price(
                    ticker=symbol,
                    date=bar["date"].date(),
                    open=_float_or_none(bar["open"]),
                    high=_float_or_none(bar["high"]),
                    low=_float_or_none(bar["low"]),
                    close=_float_or_none(bar["close"]),
                    volume=None if pd.isna(bar["volume"]) else int(bar["volume"]),
                    daily_return=_float_or_none(bar["daily_return"]),
                )
            )
        session.commit()


def _float_or_none(value: float) -> float | None:
    return None if pd.isna(value) else float(value)
