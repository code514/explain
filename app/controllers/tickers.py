from datetime import date, timedelta
from typing import cast

import pandas as pd

from app.schemas import Move, MovesResponse
from app.services import yfinance as yf_service

DEFAULT_RANGE = timedelta(days=365)

# Fetched before `start` so the first requested day has a previous close to compare with.
# A calendar week always reaches back past a weekend plus a market holiday.
PREVIOUS_CLOSE_LOOKBACK = timedelta(days=7)


class TickerNotFoundError(Exception):
    """Yahoo has no price data for the ticker in the requested range."""


class InvalidDateRangeError(Exception):
    """The start date is after the end date."""


async def get_moves(ticker: str, start: date | None, end: date | None) -> MovesResponse:
    """`end` defaults to today and `start` to a year before `end`."""
    ticker = ticker.upper()
    end = end or date.today()
    start = start or end - DEFAULT_RANGE
    if start > end:
        raise InvalidDateRangeError(f"start {start} is after end {end}")
    history = await yf_service.get_history(ticker, start - PREVIOUS_CLOSE_LOOKBACK, end)
    if history.empty:
        raise TickerNotFoundError(ticker)
    # Interim shim until move detection lives in domain/stocks.py: every trading day in the
    # requested range is reported. The lookback rows only supply the first previous close.
    daily_returns = history["close"].pct_change().loc[pd.Timestamp(start) :].dropna()
    moves = [
        Move(date=cast(pd.Timestamp, day).date(), daily_return=daily_return)
        for day, daily_return in zip(daily_returns.index, daily_returns.to_list(), strict=True)
    ]
    return MovesResponse(ticker=ticker, start=start, end=end, moves=moves)
