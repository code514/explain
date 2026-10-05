from datetime import UTC, date, datetime, timedelta
from typing import cast

import pandas as pd

from app.domain import stocks
from app.schemas import Move, TickerResponse
from app.services import cache
from app.services import yfinance as yf_service

DEFAULT_RANGE = timedelta(days=365)

# Fetched before `start` so the first requested day has a previous close to compare with.
# A calendar week always reaches back past a weekend plus a market holiday.
PREVIOUS_CLOSE_LOOKBACK = timedelta(days=7)


class TickerNotFoundError(Exception):
    """Yahoo doesn't know the ticker, or has no price data for it in the requested range."""


class InvalidDateRangeError(Exception):
    """The start date is after the end date."""


async def get_ticker(ticker: str, start: date | None, end: date | None) -> TickerResponse:
    """`end` defaults to yesterday and `start` to a year before `end`.

    Today and the future are never fetched or cached: today's bar isn't final, and a cached null
    for a day Yahoo hasn't published yet would never be refreshed. `end` is clamped to yesterday.
    """
    ticker = ticker.upper()
    yesterday = date.today() - timedelta(days=1)
    end = min(end or yesterday, yesterday)
    start = start or end - DEFAULT_RANGE
    if start > end:
        raise InvalidDateRangeError(f"start {start} is after end {end}")
    await _ensure_ticker_info(ticker)
    history_start = start - PREVIOUS_CLOSE_LOOKBACK
    history = cache.get_ticker_history(ticker, history_start, end)
    if history is None:
        history = await yf_service.get_history(ticker, history_start, end)
        if history.empty:
            raise TickerNotFoundError(ticker)
        history = stocks.calculate_returns(history)
        _cache_history(ticker, history, history_start, end)
    if history.empty:
        raise TickerNotFoundError(ticker)
    # The lookback rows only supply the first previous close.
    requested = history.loc[pd.Timestamp(start) :]
    moves = _to_moves(cast(pd.Series, requested["daily_return"]).dropna())
    major_moves = _to_moves(stocks.find_major_moves(requested))
    return TickerResponse(moves=moves, major_moves=major_moves)


async def _ensure_ticker_info(ticker: str) -> None:
    """Fetch the company metadata from Yahoo and cache it, unless it is already cached."""
    if cache.get_ticker_info(ticker) is None:
        try:
            info = await yf_service.get_info(ticker)
        except yf_service.UnknownTickerError:
            raise TickerNotFoundError(ticker) from None
        cache.save_ticker_info(info, datetime.now(UTC))


def _cache_history(ticker: str, history: pd.DataFrame, start: date, end: date) -> None:
    """Cache `history` as a contiguous daily range from `start` to `end`.

    Yahoo only returns trading days. Days without trading (weekends, holidays) are filled with
    nulls, so the cache can tell a range is complete by its first and last day.
    """
    contiguous = history.reindex(pd.date_range(start, end, freq="D", name="date"))
    cache.save_ticker_history(ticker, contiguous)


def _to_moves(daily_returns: pd.Series) -> list[Move]:
    """One `Move` per day of a `daily_return` series indexed by date."""
    return [
        Move(date=cast(pd.Timestamp, day).date(), daily_return=daily_return)
        for day, daily_return in zip(daily_returns.index, daily_returns.to_list(), strict=True)
    ]
