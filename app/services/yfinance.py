"""All yfinance interaction. Nothing else in the app imports the library.

Callers import this module as `from app.services import yfinance as yf_service`. Inside this
file, `import yfinance` resolves to the installed library (absolute imports).

yfinance is an unofficial wrapper around Yahoo's internal endpoints, so it can be rate limited
(HTTP 429) or break when Yahoo changes something. Both are handled by retrying with backoff and
by pinning the version in uv.lock.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

from app.schemas import TickerInfo

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 4
BACKOFF_SECONDS = 2.0  # doubles after each rate-limited attempt

HISTORY_COLUMNS = ["open", "high", "low", "close", "volume"]


async def get_history(ticker: str, start: date, end: date) -> pd.DataFrame:
    """Daily adjusted OHLCV for one ticker, from `start` to `end` inclusive.

    Returns a DataFrame with columns `HISTORY_COLUMNS`, indexed by trading day: a
    timezone-naive `DatetimeIndex` at midnight, named "date". Empty (same columns) if Yahoo
    has no data for the ticker or range. Call once per ticker, e.g. the stock, SPY, a sector ETF.
    """
    frame = await _with_retries(lambda: _download(ticker, start, end))
    return _normalize_history(frame)


async def get_info(ticker: str) -> TickerInfo:
    """Name, sector and industry. Slow and the most rate-limited call, so cache the result."""
    raw: dict[str, Any] = await _with_retries(lambda: yf.Ticker(ticker).info)
    return TickerInfo(
        symbol=ticker,
        name=raw.get("longName") or raw.get("shortName"),
        sector=raw.get("sector"),
        industry=raw.get("industry"),
    )


def _download(ticker: str, start: date, end: date) -> pd.DataFrame:
    return yf.Ticker(ticker).history(
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),  # Yahoo's `end` is exclusive
        interval="1d",
        auto_adjust=True,  # adjust for splits and dividends so a 10:1 split isn't a -90% move
    )


def _normalize_history(frame: pd.DataFrame) -> pd.DataFrame:
    """Lowercase columns, keep only OHLCV, naive DatetimeIndex, drop empty rows."""
    if frame.empty:
        return pd.DataFrame(columns=HISTORY_COLUMNS, index=pd.DatetimeIndex([], name="date"))
    history = frame.rename(columns=str.lower).loc[:, HISTORY_COLUMNS].dropna(how="all")
    # Daily bars are stamped at local midnight; dropping the timezone keeps the calendar day.
    history.index = pd.DatetimeIndex(history.index).tz_localize(None).rename("date")
    return history


async def _with_retries[T](call: Callable[[], T]) -> T:
    """Run a blocking yfinance call off the event loop, retrying on rate limits."""
    delay = BACKOFF_SECONDS
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return await asyncio.to_thread(call)
        except YFRateLimitError:
            if attempt == MAX_ATTEMPTS:
                raise
            logger.warning("Yahoo rate limit, retrying in %.0fs (attempt %d)", delay, attempt)
            await asyncio.sleep(delay)
            delay *= 2
    raise AssertionError("unreachable")
