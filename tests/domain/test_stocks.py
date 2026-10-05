from datetime import date
from typing import cast

import pandas as pd
import pytest

from app.domain import stocks


def _prices(daily_returns: list[float | None]) -> pd.DataFrame:
    days = pd.date_range("2025-03-03", periods=len(daily_returns), freq="D", name="date")
    return pd.DataFrame({"daily_return": daily_returns}, index=days)


def _dates(moves: pd.Series) -> list[date]:
    return [cast(pd.Timestamp, day).date() for day in moves.index]


def test_ranks_by_absolute_return_in_descending_order() -> None:
    moves = stocks.find_major_moves(_prices([0.01, -0.05, 0.03, -0.02]))

    assert moves.to_list() == [-0.05, 0.03, -0.02, 0.01]
    assert _dates(moves)[:2] == [date(2025, 3, 4), date(2025, 3, 5)]


def test_returns_only_the_top_ten() -> None:
    moves = stocks.find_major_moves(_prices([i / 100 for i in range(1, 16)]))

    assert len(moves) == 10
    assert moves.iloc[0] == pytest.approx(0.15)
    assert moves.iloc[-1] == pytest.approx(0.06)


def test_fewer_than_ten_days_returns_all_of_them() -> None:
    assert len(stocks.find_major_moves(_prices([0.01, 0.02]))) == 2


def test_skips_null_returns() -> None:
    moves = stocks.find_major_moves(_prices([None, 0.01, None]))

    assert _dates(moves) == [date(2025, 3, 4)]


def test_ties_keep_chronological_order() -> None:
    moves = stocks.find_major_moves(_prices([0.02, -0.02, 0.02]))

    assert _dates(moves) == [date(2025, 3, 3), date(2025, 3, 4), date(2025, 3, 5)]


def test_empty_frame_returns_no_moves() -> None:
    assert stocks.find_major_moves(_prices([])).empty


def _history(closes: dict[str, float]) -> pd.DataFrame:
    index = pd.DatetimeIndex(list(closes), name="date")
    return pd.DataFrame({"open": 1.0, "close": list(closes.values())}, index=index)


def test_calculate_returns_adds_a_daily_return_column() -> None:
    history = _history({"2025-02-28": 100.0, "2025-03-03": 103.0, "2025-03-04": 98.0})

    result = stocks.calculate_returns(history)

    assert list(result.columns) == ["open", "close", "daily_return"]
    assert pd.isna(result["daily_return"].iloc[0])  # no previous close
    assert result["daily_return"].iloc[1] == pytest.approx(0.03)
    assert result["daily_return"].iloc[2] == pytest.approx(98 / 103 - 1)
    assert "daily_return" not in history.columns  # the input is not modified


def test_calculate_returns_compares_with_the_previous_trading_day() -> None:
    history = _history({"2025-03-07": 100.0, "2025-03-10": 110.0})  # Friday, then Monday

    result = stocks.calculate_returns(history)

    assert result["daily_return"].iloc[1] == pytest.approx(0.10)


def test_calculate_returns_with_no_data() -> None:
    assert stocks.calculate_returns(_history({})).empty
