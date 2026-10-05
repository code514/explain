from datetime import date, timedelta

import pandas as pd
import pytest

from app.controllers import tickers
from app.services import yfinance as yf_service


def _history(*days: str, closes: list[float] | None = None) -> pd.DataFrame:
    index = pd.DatetimeIndex(days, name="date")
    close = closes if closes is not None else [1.0] * len(days)
    return pd.DataFrame(
        {"open": 1.0, "high": 1.0, "low": 1.0, "close": close, "volume": 1}, index=index
    )


async def test_get_moves_fetches_prices_for_uppercased_ticker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, date, date]] = []

    async def fake_get_history(ticker: str, start: date, end: date) -> pd.DataFrame:
        calls.append((ticker, start, end))
        return _history("2025-03-03")

    monkeypatch.setattr(yf_service, "get_history", fake_get_history)

    response = await tickers.get_moves("nvda", date(2025, 3, 1), date(2025, 3, 5))

    assert calls == [("NVDA", date(2025, 3, 1) - tickers.PREVIOUS_CLOSE_LOOKBACK, date(2025, 3, 5))]
    assert response.ticker == "NVDA"


async def test_get_moves_unknown_ticker(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_data(ticker: str, start: date, end: date) -> pd.DataFrame:
        return _history()

    monkeypatch.setattr(yf_service, "get_history", no_data)

    with pytest.raises(tickers.TickerNotFoundError):
        await tickers.get_moves("BOGUS", date(2025, 3, 1), date(2025, 3, 5))


async def test_get_moves_defaults_to_the_last_year(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, date, date]] = []

    async def fake_get_history(ticker: str, start: date, end: date) -> pd.DataFrame:
        calls.append((ticker, start, end))
        return _history("2025-03-03")

    monkeypatch.setattr(yf_service, "get_history", fake_get_history)

    response = await tickers.get_moves("NVDA", None, None)

    today = date.today()
    assert response.end == today
    assert response.start == today - tickers.DEFAULT_RANGE
    assert calls == [("NVDA", response.start - tickers.PREVIOUS_CLOSE_LOOKBACK, response.end)]


async def test_get_moves_start_defaults_relative_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_history(ticker: str, start: date, end: date) -> pd.DataFrame:
        return _history("2025-03-03")

    monkeypatch.setattr(yf_service, "get_history", fake_get_history)

    response = await tickers.get_moves("NVDA", None, date(2025, 3, 5))

    assert response.start == date(2025, 3, 5) - tickers.DEFAULT_RANGE


async def test_get_moves_rejects_inverted_range() -> None:
    with pytest.raises(tickers.InvalidDateRangeError):
        await tickers.get_moves("NVDA", date(2025, 3, 5), date(2025, 3, 1))


async def test_get_moves_rejects_start_in_the_future() -> None:
    with pytest.raises(tickers.InvalidDateRangeError):
        await tickers.get_moves("NVDA", date.today() + timedelta(days=1), None)


async def test_get_moves_reports_daily_returns_from_the_first_requested_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_history(ticker: str, start: date, end: date) -> pd.DataFrame:
        # Friday is the lookback row. Monday is the first requested day.
        return _history("2025-02-28", "2025-03-03", "2025-03-04", closes=[100.0, 103.0, 98.0])

    monkeypatch.setattr(yf_service, "get_history", fake_get_history)

    response = await tickers.get_moves("NVDA", date(2025, 3, 3), date(2025, 3, 4))

    assert [move.date for move in response.moves] == [date(2025, 3, 3), date(2025, 3, 4)]
    assert response.moves[0].daily_return == pytest.approx(0.03)
    assert response.moves[1].daily_return == pytest.approx(98 / 103 - 1)
