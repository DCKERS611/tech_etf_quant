import pandas as pd

from tech_etf_quant.portfolio import Portfolio
from tech_etf_quant.report import generate_daily_report


def test_daily_report_files_are_created(tmp_path):
    ranking = pd.DataFrame(
        [
            {
                "date": "2024-07-01",
                "symbol": "512480",
                "name": "半导体ETF",
                "group": "semiconductor",
                "close": 1.2,
                "pct_change": 0.01,
                "r5": 0.02,
                "r20": 0.08,
                "r60": 0.15,
                "ma20": 1.1,
                "ma60": 1.0,
                "vol20": 0.01,
                "volume_boost": 1.4,
                "relative_strength": 0.03,
                "overheat_penalty": 0,
                "score": 0.1,
                "rank_all": 1,
                "rank_group": 1,
                "trend_ok": True,
            },
            {
                "date": "2024-07-01",
                "symbol": "588000",
                "name": "科创50ETF",
                "group": "benchmark",
                "close": 1.0,
                "pct_change": 0.0,
                "r5": 0.0,
                "r20": 0.02,
                "r60": 0.04,
                "ma20": 1.0,
                "ma60": 0.99,
                "vol20": 0.01,
                "volume_boost": 1.0,
                "relative_strength": 0.0,
                "overheat_penalty": 0,
                "score": 0.02,
                "rank_all": 2,
                "rank_group": 1,
                "trend_ok": True,
            },
        ]
    )
    paths = generate_daily_report("2024-07-01", ranking=ranking, portfolio=Portfolio(), output_dir=tmp_path)
    assert paths["markdown"].exists()
    assert paths["html"].exists()
    assert "每日交易报告" in paths["markdown"].read_text(encoding="utf-8")
