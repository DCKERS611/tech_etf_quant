import numpy as np
import pandas as pd

from tech_etf_quant.indicators import add_indicators
from tech_etf_quant.scoring import calculate_scores


def make_df(symbol, start, end, amount=60_000_000):
    n = 150
    close = np.linspace(start, end, n)
    df = pd.DataFrame(
        {
            "date": pd.bdate_range("2024-01-01", periods=n).strftime("%Y-%m-%d"),
            "symbol": symbol,
            "open": close * 0.995,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": amount / close,
            "amount": amount,
            "amplitude": 0.02,
            "pct_change": pd.Series(close).pct_change().fillna(0),
            "change": pd.Series(close).diff().fillna(0),
            "turnover": 0.01,
        }
    )
    return add_indicators(df)


def pool():
    return pd.DataFrame(
        [
            {"symbol": "512480", "name": "强趋势ETF", "group": "semiconductor", "role": "core", "enabled": True},
            {"symbol": "159995", "name": "弱趋势ETF", "group": "semiconductor", "role": "core", "enabled": True},
            {"symbol": "588000", "name": "基准", "group": "benchmark", "role": "benchmark", "enabled": True},
        ]
    )


def test_strong_trend_scores_higher_and_group_rank_is_correct():
    data = {
        "512480": make_df("512480", 1, 2),
        "159995": make_df("159995", 1, 1.1),
        "588000": make_df("588000", 1, 1.3),
    }
    ranking = calculate_scores(data, pool(), target_date="2024-07-26")
    assert ranking.iloc[0]["symbol"] == "512480"
    assert int(ranking[ranking["symbol"] == "512480"].iloc[0]["rank_group"]) == 1


def test_overheat_penalty_lowers_score():
    data = {
        "512480": make_df("512480", 1, 2),
        "159995": make_df("159995", 1, 2),
        "588000": make_df("588000", 1, 1.3),
    }
    data["512480"].loc[data["512480"].index[-1], "pct_change"] = 0.08
    data["159995"].loc[data["159995"].index[-1], "pct_change"] = 0.01
    ranking = calculate_scores(data, pool(), target_date="2024-07-26")
    hot = ranking[ranking["symbol"] == "512480"].iloc[0]["score"]
    calm = ranking[ranking["symbol"] == "159995"].iloc[0]["score"]
    assert hot < calm


def test_low_liquidity_etf_is_filtered():
    data = {
        "512480": make_df("512480", 1, 2, amount=1_000_000),
        "159995": make_df("159995", 1, 1.5),
        "588000": make_df("588000", 1, 1.3),
    }
    ranking = calculate_scores(data, pool(), target_date="2024-07-26")
    assert "512480" not in set(ranking["symbol"])
