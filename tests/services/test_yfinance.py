from datetime import date
from typing import Any

import pandas as pd
import pytest
from yfinance.exceptions import YFRateLimitError

from app.services import yfinance as yf_service


def _frame(dates: list[str]) -> pd.DataFrame:
    """Shaped like Ticker.history(): capitalized columns, tz-aware index, extra columns."""
    index = pd.DatetimeIndex(dates, tz="America/New_York", name="Date")
    frame = pd.DataFrame(
        {
            "Open": [100.0 + i for i in range(len(index))],
            "High": 101.0,
            "Low": 99.0,
            "Close": [100.5 + i for i in range(len(index))],
            "Volume": 1_000,
            "Dividends": 0.0,
            "Stock Splits": 0.0,
        },
        index=index,
    )
    return frame


class FakeTicker:
    """Stands in for yf.Ticker. `history_calls` records the arguments of each history() call."""

    history_calls: list[dict[str, Any]] = []
    history_result: pd.DataFrame = pd.DataFrame()
    info: dict[str, Any] = {}

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    def history(self, **kwargs: Any) -> pd.DataFrame:
        FakeTicker.history_calls.append({"symbol": self.symbol, **kwargs})
        return FakeTicker.history_result


@pytest.fixture(autouse=True)
def fake_yfinance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(yf_service, "BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(yf_service.yf, "Ticker", FakeTicker)
    FakeTicker.history_calls = []
    FakeTicker.history_result = pd.DataFrame()
    FakeTicker.info = {}


async def test_get_history_returns_ohlcv_with_naive_datetime_index() -> None:
    FakeTicker.history_result = _frame(["2025-03-03", "2025-03-04"])

    history = await yf_service.get_history("NVDA", date(2025, 3, 3), date(2025, 3, 4))

    [call] = FakeTicker.history_calls
    assert call["symbol"] == "NVDA"
    assert call["end"] == "2025-03-05"  # Yahoo's end is exclusive
    assert call["auto_adjust"] is True
    assert list(history.columns) == yf_service.HISTORY_COLUMNS
    assert isinstance(history.index, pd.DatetimeIndex)
    assert history.index.tz is None
    assert history.index.name == "date"
    assert list(history.index) == [pd.Timestamp("2025-03-03"), pd.Timestamp("2025-03-04")]
    assert history.loc["2025-03-04", "close"] == 101.5


async def test_get_history_drops_empty_rows() -> None:
    frame = _frame(["2025-03-03", "2025-03-04"])
    frame.loc[frame.index[1], ["Open", "High", "Low", "Close", "Volume"]] = float("nan")
    FakeTicker.history_result = frame

    history = await yf_service.get_history("NVDA", date(2025, 3, 3), date(2025, 3, 4))

    assert list(history.index) == [pd.Timestamp("2025-03-03")]


async def test_get_history_empty_for_unknown_ticker() -> None:
    history = await yf_service.get_history("BOGUS", date(2025, 3, 3), date(2025, 3, 4))

    assert history.empty
    assert list(history.columns) == yf_service.HISTORY_COLUMNS
    assert isinstance(history.index, pd.DatetimeIndex)


async def test_rate_limit_is_retried_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def flaky(self: FakeTicker, **_: Any) -> pd.DataFrame:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise YFRateLimitError()
        return _frame(["2025-03-03"])

    monkeypatch.setattr(FakeTicker, "history", flaky)

    history = await yf_service.get_history("NVDA", date(2025, 3, 3), date(2025, 3, 3))

    assert attempts == 3
    assert len(history) == 1


async def test_rate_limit_gives_up(monkeypatch: pytest.MonkeyPatch) -> None:
    def always_limited(self: FakeTicker, **_: Any) -> pd.DataFrame:
        raise YFRateLimitError()

    monkeypatch.setattr(FakeTicker, "history", always_limited)

    with pytest.raises(YFRateLimitError):
        await yf_service.get_history("NVDA", date(2025, 3, 3), date(2025, 3, 3))


async def test_get_info() -> None:
    FakeTicker.info = {"longName": "NVIDIA Corporation", "sector": "Technology"}

    info = await yf_service.get_info("NVDA")

    assert info.name == "NVIDIA Corporation"
    assert info.sector == "Technology"
    assert info.industry is None
