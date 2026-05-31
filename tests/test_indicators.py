import numpy as np
import pandas as pd

from tech_etf_quant.indicators import add_indicators


def make_price_df(n=80):
    close = np.arange(1, n + 1, dtype=float)
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2024-01-01", periods=n).strftime("%Y-%m-%d"),
            "symbol": "512480",
            "open": close,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
            "volume": 1_000_000,
            "amount": 50_000_000,
            "amplitude": 0.01,
            "pct_change": pd.Series(close).pct_change().fillna(0),
            "change": pd.Series(close).diff().fillna(0),
            "turnover": 0.01,
        }
    )


def test_indicators_are_correct():
    out = add_indicators(make_price_df())
    assert out.loc[19, "ma20"] == np.mean(np.arange(1, 21))
    assert out.loc[59, "ma60"] == np.mean(np.arange(1, 61))
    assert out.loc[5, "r5"] == 6 / 1 - 1
    assert out.loc[20, "r20"] == 21 / 1 - 1
    assert out.loc[60, "r60"] == 61 / 1 - 1
    assert pd.notna(out.loc[20, "vol20"])


def test_indicators_do_not_use_future_data():
    base = make_price_df()
    changed = base.copy()
    changed.loc[79, "close"] = 999
    out_base = add_indicators(base)
    out_changed = add_indicators(changed)
    pd.testing.assert_series_equal(out_base.loc[40, ["ma20", "ma60", "r20"]], out_changed.loc[40, ["ma20", "ma60", "r20"]])
