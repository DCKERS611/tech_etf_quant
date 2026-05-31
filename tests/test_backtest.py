import numpy as np
import pandas as pd

from tech_etf_quant.backtest import run_backtest
from tech_etf_quant.indicators import add_indicators


def make_backtest_df(symbol, slope):
    n = 170
    close = 1 + np.arange(n) * slope
    open_ = close + 0.002
    df = pd.DataFrame(
        {
            "date": pd.bdate_range("2024-01-01", periods=n).strftime("%Y-%m-%d"),
            "symbol": symbol,
            "open": open_,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 30_000_000,
            "amount": 50_000_000,
            "amplitude": 0.02,
            "pct_change": pd.Series(close).pct_change().fillna(0),
            "change": pd.Series(close).diff().fillna(0),
            "turnover": 0.01,
        }
    )
    return add_indicators(df)


def test_backtest_outputs_and_next_open_execution(tmp_path):
    pool = pd.DataFrame(
        [
            {"symbol": "512480", "name": "半导体ETF", "group": "semiconductor", "role": "core", "enabled": True},
            {"symbol": "588000", "name": "科创50ETF", "group": "benchmark", "role": "benchmark", "enabled": True},
        ]
    )
    data = {"512480": make_backtest_df("512480", 0.004), "588000": make_backtest_df("588000", 0.001)}
    result = run_backtest(
        "2024-01-01",
        "2024-08-23",
        data_by_symbol=data,
        etf_pool=pool,
        output_dir=tmp_path,
        write_outputs=False,
    )
    equity = result["equity_curve"]
    trades = result["trades"]
    assert len(equity) == 170
    assert not trades.empty
    first_buy = trades[trades["side"] == "BUY"].iloc[0]
    row = data[first_buy["symbol"]][data[first_buy["symbol"]]["date"] == first_buy["date"]].iloc[0]
    assert first_buy["price"] == round(round(float(row["open"]) * 1.0003 / 0.001) * 0.001, 3)
    for key in ["cumulative_return", "max_drawdown", "trade_count", "relative_588000"]:
        assert key in result["performance"]
