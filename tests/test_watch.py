import pandas as pd

from tech_etf_quant.watch import evaluate_snapshot_row, run_watch


def realtime_df(source="akshare_realtime"):
    return pd.DataFrame(
        [
            {
                "date": "2026-05-31",
                "time": "10:35",
                "symbol": "512480",
                "name": "半导体ETF",
                "price": 1.05,
                "pct_change": 0.035,
                "amount": 50_000_000,
                "volume": 10_000_000,
                "high": 1.06,
                "low": 1.01,
                "open": 1.02,
                "prev_close": 1.00,
                "source": source,
                "source_time": "2026-05-31 10:35:00",
                "note": source,
            }
        ]
    )


def test_watch_uses_auto_realtime_first(monkeypatch):
    monkeypatch.setattr("tech_etf_quant.watch.refresh_realtime", lambda date, time: realtime_df())
    monkeypatch.setattr("tech_etf_quant.watch.read_realtime_cache", lambda date, time: pd.DataFrame())
    result = run_watch("2026-05-31", "10:35")
    assert not result.empty
    assert result.iloc[0]["source"] == "akshare_realtime"


def test_watch_falls_back_to_cache_before_manual(monkeypatch, tmp_path):
    manual = tmp_path / "manual.csv"
    pd.DataFrame(
        [
            {
                "date": "2026-05-31",
                "time": "10:35",
                "symbol": "159995",
                "price": 2.0,
                "pct_change": 0.0,
                "amount": 1,
                "volume": 1,
                "high": 2.0,
                "low": 2.0,
                "open": 2.0,
                "prev_close": 2.0,
                "note": "manual",
            }
        ]
    ).to_csv(manual, index=False)
    monkeypatch.setattr("tech_etf_quant.watch.refresh_realtime", lambda date, time: pd.DataFrame())
    monkeypatch.setattr("tech_etf_quant.watch.read_realtime_cache", lambda date, time: realtime_df("local_cache"))
    result = run_watch("2026-05-31", "10:35", manual)
    assert result.iloc[0]["symbol"] == "512480"
    assert result.iloc[0]["source"] == "local_cache"


def test_new_fixed_watch_times_decisions():
    row = pd.Series({"pct_change": 0.045, "open": 1.0, "prev_close": 1.0, "price": 1.04, "high": 1.05})
    status, decision = evaluate_snapshot_row(row, "10:35")
    assert status == "CHASE_BLOCK"
    assert "10:35" in decision
    row["pct_change"] = 0.061
    status, decision = evaluate_snapshot_row(row, "14:35")
    assert status == "ONLY_TEST"
