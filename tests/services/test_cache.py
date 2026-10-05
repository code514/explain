import datetime as dt

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from app.schemas import TickerInfo
from app.services import cache
from app.services.yfinance import HISTORY_COLUMNS

pytestmark = pytest.mark.usefixtures("db")


def _history(*days: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [1.5 + i for i in range(len(days))],
            "high": 2.0,
            "low": 1.0,
            "close": [1.75 + i for i in range(len(days))],
            "volume": [100 + i for i in range(len(days))],
            "daily_return": [0.01 * i for i in range(len(days))],
        },
        index=pd.DatetimeIndex(days, name="date").astype("datetime64[ns]"),
    )


def test_info_miss_returns_none() -> None:
    assert cache.get_ticker_info("NVDA") is None


def test_info_round_trip_and_overwrite() -> None:
    now = dt.datetime(2025, 3, 3, 12, 0, tzinfo=dt.UTC)
    cache.save_ticker_info(TickerInfo(symbol="NVDA", name="Nvidia", sector="Tech"), now)
    assert cache.get_ticker_info("NVDA") == TickerInfo(symbol="NVDA", name="Nvidia", sector="Tech")

    cache.save_ticker_info(TickerInfo(symbol="NVDA", name="NVIDIA Corp"), now)
    info = cache.get_ticker_info("NVDA")
    assert info is not None
    assert info.name == "NVIDIA Corp"
    assert info.sector is None


def test_history_round_trips_in_yfinance_format() -> None:
    saved = _history("2025-03-03", "2025-03-04", "2025-03-05")
    cache.save_ticker_history("NVDA", saved)

    loaded = cache.get_ticker_history("NVDA", dt.date(2025, 3, 3), dt.date(2025, 3, 5))

    assert loaded is not None
    assert list(loaded.columns) == [*HISTORY_COLUMNS, "daily_return"]
    assert loaded.index.name == "date"
    assert_frame_equal(loaded, saved, check_dtype=False, check_freq=False)


def test_history_returns_only_requested_range() -> None:
    cache.save_ticker_history("NVDA", _history("2025-03-03", "2025-03-04", "2025-03-05"))

    loaded = cache.get_ticker_history("NVDA", dt.date(2025, 3, 3), dt.date(2025, 3, 4))

    assert loaded is not None
    assert list(loaded.index) == [pd.Timestamp("2025-03-03"), pd.Timestamp("2025-03-04")]


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (dt.date(2025, 3, 2), dt.date(2025, 3, 5)),  # start not stored
        (dt.date(2025, 3, 3), dt.date(2025, 3, 6)),  # end not stored
        (dt.date(2025, 3, 10), dt.date(2025, 3, 11)),  # neither stored
    ],
)
def test_history_miss_returns_none(start: dt.date, end: dt.date) -> None:
    cache.save_ticker_history("NVDA", _history("2025-03-03", "2025-03-04", "2025-03-05"))
    assert cache.get_ticker_history("NVDA", start, end) is None


def test_history_drops_null_days_on_read() -> None:
    saved = _history("2025-03-07", "2025-03-08", "2025-03-09", "2025-03-10")
    saved.loc[["2025-03-08", "2025-03-09"]] = float("nan")  # a weekend
    cache.save_ticker_history("NVDA", saved)

    loaded = cache.get_ticker_history("NVDA", dt.date(2025, 3, 7), dt.date(2025, 3, 10))

    assert loaded is not None
    assert_frame_equal(
        loaded,
        saved.drop(pd.to_datetime(["2025-03-08", "2025-03-09"])),
        check_dtype=False,
        check_freq=False,
    )


def test_history_with_only_null_days_is_a_hit_with_an_empty_frame() -> None:
    saved = _history("2025-03-08", "2025-03-09").astype(float)
    saved[:] = float("nan")
    cache.save_ticker_history("NVDA", saved)

    loaded = cache.get_ticker_history("NVDA", dt.date(2025, 3, 8), dt.date(2025, 3, 9))

    assert loaded is not None
    assert loaded.empty


def test_history_is_per_ticker() -> None:
    cache.save_ticker_history("NVDA", _history("2025-03-03", "2025-03-05"))
    assert cache.get_ticker_history("SPY", dt.date(2025, 3, 3), dt.date(2025, 3, 5)) is None


def test_saving_history_again_overwrites_days() -> None:
    cache.save_ticker_history("NVDA", _history("2025-03-03"))
    cache.save_ticker_history("NVDA", _history("2025-03-03", "2025-03-04"))

    loaded = cache.get_ticker_history("NVDA", dt.date(2025, 3, 3), dt.date(2025, 3, 4))
    assert loaded is not None
    assert len(loaded) == 2
