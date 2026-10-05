"""Pure stock-market logic on plain data: no I/O, no clock."""

from typing import cast

import pandas as pd

MAJOR_MOVE_COUNT = 10


def find_major_moves(prices: pd.DataFrame, count: int = MAJOR_MOVE_COUNT) -> pd.Series:
    """The `count` days with the biggest up or down move, biggest first.

    Returns the `daily_return` of those days as a Series indexed by date.

    `prices` needs a `daily_return` column (fraction, 0.03 = up 3%) and a DatetimeIndex of days.
    Days with a null `daily_return` are skipped. Ranked by absolute value, so a -5% day outranks
    a +3% day. Equal moves keep their original (chronological) order.
    """
    daily_returns = cast(pd.Series, prices["daily_return"]).dropna()
    by_size = daily_returns.abs().sort_values(ascending=False, kind="stable")
    return daily_returns.loc[by_size.index[:count]]


def calculate_returns(history: pd.DataFrame) -> pd.DataFrame:
    """`history` with a `daily_return` column added: the fraction the close moved since the
    previous trading day's close (0.03 = up 3%).

    `history` is a `yf_service.get_history` frame (trading days only). Its first day has no
    previous close, so its `daily_return` is null.
    """
    return history.assign(daily_return=history["close"].pct_change())
