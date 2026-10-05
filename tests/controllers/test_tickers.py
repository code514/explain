from datetime import date, timedelta

import pandas as pd
import pytest
from sqlmodel import Session, col, select

from app.controllers import tickers
from app.db import get_engine
from app.models import Price
from app.schemas import TickerInfo
from app.services import cache
from app.services import yfinance as yf_service

pytestmark = pytest.mark.usefixtures("db")


@pytest.fixture(autouse=True)
def stub_info(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Stub `yf_service.get_info`; returns the tickers it was called with."""
    calls: list[str] = []

    async def fake_get_info(ticker: str) -> TickerInfo:
        calls.append(ticker)
        return TickerInfo(symbol=ticker, name="Test Corp")

    monkeypatch.setattr(yf_service, "get_info", fake_get_info)
    return calls


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
        return _history(end.isoformat())

    monkeypatch.setattr(yf_service, "get_history", fake_get_history)

    response = await tickers.get_moves("NVDA", None, None)

    yesterday = date.today() - timedelta(days=1)
    assert response.end == yesterday
    assert response.start == yesterday - tickers.DEFAULT_RANGE
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


async def test_get_moves_fetches_and_caches_info_once(
    monkeypatch: pytest.MonkeyPatch, stub_info: list[str]
) -> None:
    async def fake_get_history(ticker: str, start: date, end: date) -> pd.DataFrame:
        return _history("2025-03-03")

    monkeypatch.setattr(yf_service, "get_history", fake_get_history)

    await tickers.get_moves("nvda", date(2025, 3, 1), date(2025, 3, 5))
    await tickers.get_moves("nvda", date(2025, 3, 1), date(2025, 3, 5))

    assert stub_info == ["NVDA"]
    assert cache.get_ticker_info("NVDA") == TickerInfo(symbol="NVDA", name="Test Corp")


async def test_get_moves_uses_cached_history_on_second_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, date, date]] = []

    async def fake_get_history(ticker: str, start: date, end: date) -> pd.DataFrame:
        calls.append((ticker, start, end))
        # Covers both edges: the lookback start (Mon 02-24) and the end (Tue 03-04).
        return _history(
            "2025-02-24", "2025-02-28", "2025-03-03", "2025-03-04", closes=[1.0, 100.0, 103.0, 98.0]
        )

    monkeypatch.setattr(yf_service, "get_history", fake_get_history)

    first = await tickers.get_moves("NVDA", date(2025, 3, 3), date(2025, 3, 4))
    second = await tickers.get_moves("NVDA", date(2025, 3, 3), date(2025, 3, 4))

    assert len(calls) == 1
    assert second == first


async def test_get_moves_caches_a_contiguous_range_with_nulls_for_missing_days(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_history(ticker: str, start: date, end: date) -> pd.DataFrame:
        # Fri 03-07 and Mon 03-10 only: the weekend between them is missing.
        return _history("2025-03-07", "2025-03-10", closes=[100.0, 110.0])

    monkeypatch.setattr(yf_service, "get_history", fake_get_history)

    response = await tickers.get_moves("NVDA", date(2025, 3, 7), date(2025, 3, 10))

    with Session(get_engine()) as session:
        rows = session.exec(
            select(Price).where(Price.ticker == "NVDA").order_by(col(Price.date))
        ).all()
    assert [row.date for row in rows] == [
        d.date() for d in pd.date_range("2025-02-28", "2025-03-10")
    ]
    assert [row.close for row in rows if row.date.weekday() >= 5] == [None, None, None, None]
    assert [row.close for row in rows if row.date.isoformat() == "2025-03-07"] == [100.0]
    # 03-07 has no previous close in the data, so only Monday has a return, measured from Friday.
    assert [move.date for move in response.moves] == [date(2025, 3, 10)]
    assert response.moves[0].daily_return == pytest.approx(0.10)


async def test_get_moves_on_a_weekend_range_hits_the_cache_on_the_second_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, date, date]] = []

    async def fake_get_history(ticker: str, start: date, end: date) -> pd.DataFrame:
        calls.append((ticker, start, end))
        return _history("2025-02-28", "2025-03-03", closes=[100.0, 101.0])

    monkeypatch.setattr(yf_service, "get_history", fake_get_history)

    # Both `start` and `end` fall on a weekend, so neither is a trading day.
    await tickers.get_moves("NVDA", date(2025, 3, 8), date(2025, 3, 9))
    await tickers.get_moves("NVDA", date(2025, 3, 8), date(2025, 3, 9))

    assert len(calls) == 1


async def test_get_moves_does_not_cache_an_unknown_ticker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_data(ticker: str, start: date, end: date) -> pd.DataFrame:
        return _history()

    monkeypatch.setattr(yf_service, "get_history", no_data)

    with pytest.raises(tickers.TickerNotFoundError):
        await tickers.get_moves("BOGUS", date(2025, 3, 1), date(2025, 3, 5))

    start = date(2025, 3, 1) - tickers.PREVIOUS_CLOSE_LOOKBACK
    assert cache.get_ticker_history("BOGUS", start, date(2025, 3, 5)) is None


async def test_get_moves_clamps_end_to_yesterday(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, date, date]] = []

    async def fake_get_history(ticker: str, start: date, end: date) -> pd.DataFrame:
        calls.append((ticker, start, end))
        return _history(end.isoformat())

    monkeypatch.setattr(yf_service, "get_history", fake_get_history)
    yesterday = date.today() - timedelta(days=1)

    response = await tickers.get_moves("NVDA", yesterday - timedelta(days=5), date.today())
    future = await tickers.get_moves(
        "NVDA", yesterday - timedelta(days=5), date.today() + timedelta(days=30)
    )

    assert response.end == yesterday
    assert future.end == yesterday
    assert all(end == yesterday for _, _, end in calls)


async def test_get_moves_rejects_start_today(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(tickers.InvalidDateRangeError):
        await tickers.get_moves("NVDA", date.today(), None)


async def test_get_moves_unknown_ticker_by_info(monkeypatch: pytest.MonkeyPatch) -> None:
    async def unknown(ticker: str) -> TickerInfo:
        raise yf_service.UnknownTickerError(ticker)

    async def fail_get_history(ticker: str, start: date, end: date) -> pd.DataFrame:
        raise AssertionError("history must not be fetched for an unknown ticker")

    monkeypatch.setattr(yf_service, "get_info", unknown)
    monkeypatch.setattr(yf_service, "get_history", fail_get_history)

    with pytest.raises(tickers.TickerNotFoundError):
        await tickers.get_moves("BOGUS", date(2025, 3, 1), date(2025, 3, 5))

    assert cache.get_ticker_info("BOGUS") is None
