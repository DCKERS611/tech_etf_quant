from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from tech_etf_quant.deployment import run_deploy_health_check
from tech_etf_quant.indicators import add_indicators
from tech_etf_quant.portfolio import Portfolio
from tech_etf_quant.risk import evaluate_trade_permission
from tech_etf_quant.risk_state import load_risk_state, save_risk_state, state_from_portfolio
from tech_etf_quant.scheduler import due_watch_times, refresh_plan
from tech_etf_quant.scoring import calculate_scores
from tech_etf_quant.signal_center import build_signal_center
from tech_etf_quant.strategy_registry import pick_best_candidate


def make_ranked_data(symbol: str, start: float, end: float, amount: float = 80_000_000) -> pd.DataFrame:
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
    out = add_indicators(df)
    out.loc[out.index[-1], "volume_boost"] = 1.6
    return out


def pool() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"symbol": "512480", "name": "半导体ETF", "group": "semiconductor", "role": "core", "enabled": True},
            {"symbol": "159995", "name": "芯片ETF", "group": "semiconductor", "role": "core", "enabled": True},
            {"symbol": "588000", "name": "科创50ETF", "group": "benchmark", "role": "benchmark", "enabled": True},
        ]
    )


def ranking() -> pd.DataFrame:
    data = {
        "512480": make_ranked_data("512480", 1.0, 2.0),
        "159995": make_ranked_data("159995", 1.0, 1.2),
        "588000": make_ranked_data("588000", 1.0, 1.25),
    }
    return calculate_scores(data, pool(), target_date="2024-07-26")


def test_strategy_registry_picks_actionable_candidate():
    row = ranking().iloc[0]
    risk = evaluate_trade_permission(Portfolio(), pct_change=float(row["pct_change"]), watch_time="14:35")
    candidate = pick_best_candidate(row, risk)

    assert candidate.signal.signal_type.startswith("BUY")
    assert candidate.confidence > 0


def test_signal_center_builds_explainable_rows():
    center = build_signal_center("2024-07-26", ranking=ranking(), portfolio=Portfolio(), save=False)

    assert not center.empty
    assert {"signal_type", "confidence", "explain", "risk_permission"}.issubset(center.columns)
    assert center.iloc[0]["signal_rank"] == 1


def test_risk_state_round_trip(tmp_path):
    portfolio = Portfolio()
    portfolio.consecutive_losses = 2
    state = state_from_portfolio(portfolio, notes=["test"])
    path = tmp_path / "risk_state.json"
    save_risk_state(state, path=path, append_history=False)
    loaded = load_risk_state(path)

    assert loaded.only_test is True
    assert loaded.notes == ["test"]


def test_scheduler_marks_due_slots():
    plan = refresh_plan(now=datetime(2024, 7, 26, 10, 40), target_date="2024-07-26")
    due = due_watch_times(now=datetime(2024, 7, 26, 10, 40), target_date="2024-07-26")

    assert "09:35" in set(plan[plan["state"] == "due"]["time"])
    assert "10:35" in due
    assert "11:30" not in due


def test_deployment_health_payload(tmp_path):
    payload = run_deploy_health_check(output_dir=tmp_path)

    assert payload["main_file_path"] == "app/streamlit_app.py"
    assert (tmp_path / "streamlit_health.json").exists()
