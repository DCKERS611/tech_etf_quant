"""ETF scoring and ranking."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import DAILY_REPORT_DIR, Settings, load_etf_pool, load_settings
from .data_loader import ensure_sample_data, latest_available_date, load_processed_data
from .indicators import add_indicators

RANKING_COLUMNS = [
    "date",
    "symbol",
    "name",
    "group",
    "close",
    "pct_change",
    "r5",
    "r20",
    "r60",
    "ma20",
    "ma60",
    "vol20",
    "volume_boost",
    "relative_strength",
    "overheat_penalty",
    "score",
    "rank_all",
    "rank_group",
    "trend_ok",
]


def _latest_row_on_or_before(df: pd.DataFrame, target_date: str | None) -> pd.Series | None:
    if df.empty:
        return None
    work = df.copy()
    if "ma20" not in work.columns:
        work = add_indicators(work)
    if target_date is not None:
        work = work[work["date"] <= target_date]
    if work.empty:
        return None
    return work.sort_values("date").iloc[-1]


def calculate_scores(
    data_by_symbol: dict[str, pd.DataFrame],
    etf_pool: pd.DataFrame | None = None,
    target_date: str | None = None,
    settings: Settings | None = None,
) -> pd.DataFrame:
    settings = settings or load_settings()
    etf_pool = etf_pool if etf_pool is not None else load_etf_pool(enabled_only=True)
    min_history_days = int(settings.get("filters.min_history_days", 120))
    min_avg_amount = float(settings.get("filters.min_avg_amount", 30_000_000))
    benchmark_symbols = [str(s).zfill(6) for s in settings.get("report.benchmark_symbols", ["588000"])]
    rows: list[dict] = []
    pool_lookup = etf_pool.set_index("symbol").to_dict("index")
    benchmark_r20 = 0.0
    for benchmark in benchmark_symbols:
        row = _latest_row_on_or_before(data_by_symbol.get(benchmark, pd.DataFrame()), target_date)
        if row is not None and pd.notna(row.get("r20")):
            benchmark_r20 = float(row["r20"])
            break
    for symbol, meta in pool_lookup.items():
        df = data_by_symbol.get(symbol, pd.DataFrame())
        history = df[df["date"] <= target_date] if target_date is not None and "date" in df.columns else df
        if len(history) < min_history_days:
            continue
        row = _latest_row_on_or_before(history, target_date)
        if row is None:
            continue
        amount_ma20 = float(row.get("amount_ma20", np.nan))
        is_benchmark = meta.get("group") == "benchmark"
        if (not is_benchmark) and (pd.isna(amount_ma20) or amount_ma20 < min_avg_amount):
            continue
        r5 = float(row.get("r5", 0) or 0)
        r20 = float(row.get("r20", 0) or 0)
        r60 = float(row.get("r60", 0) or 0)
        vol20 = float(row.get("vol20", 0) or 0)
        pct_change = float(row.get("pct_change", 0) or 0)
        volume_boost = float(row.get("volume_boost", 1) or 1)
        volume_boost_score = min(volume_boost - 1, 1)
        relative_strength = r20 - benchmark_r20
        overheat_penalty = max(pct_change - 0.04, 0)
        score = (
            0.30 * r20
            + 0.25 * r60
            + 0.15 * r5
            + 0.15 * volume_boost_score
            + 0.15 * relative_strength
            - 0.20 * vol20
            - 0.20 * overheat_penalty
        )
        rows.append(
            {
                "date": row["date"],
                "symbol": symbol,
                "name": meta.get("name", ""),
                "group": meta.get("group", ""),
                "close": float(row["close"]),
                "pct_change": pct_change,
                "r5": r5,
                "r20": r20,
                "r60": r60,
                "ma20": float(row.get("ma20", np.nan)),
                "ma60": float(row.get("ma60", np.nan)),
                "vol20": vol20,
                "volume_boost": volume_boost,
                "relative_strength": relative_strength,
                "overheat_penalty": overheat_penalty,
                "score": float(score),
                "trend_ok": bool(row.get("trend_ok", False)),
            }
        )
    ranking = pd.DataFrame(rows)
    if ranking.empty:
        return pd.DataFrame(columns=RANKING_COLUMNS)
    ranking = ranking.sort_values("score", ascending=False).reset_index(drop=True)
    ranking["rank_all"] = np.arange(1, len(ranking) + 1)
    ranking["rank_group"] = ranking.groupby("group")["score"].rank(method="first", ascending=False).astype(int)
    return ranking[RANKING_COLUMNS]


def save_ranking(ranking: pd.DataFrame, target_date: str | None = None, output_dir: Path | None = None) -> Path:
    output_dir = output_dir or DAILY_REPORT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    if target_date is None:
        target_date = str(ranking["date"].max()) if not ranking.empty else "unknown"
    path = output_dir / f"{target_date}_ranking.csv"
    ranking.to_csv(path, index=False, encoding="utf-8")
    return path


def score_latest(target_date: str | None = None, save: bool = True) -> pd.DataFrame:
    data = load_processed_data()
    if not data:
        data = ensure_sample_data()
    if target_date is None:
        target_date = latest_available_date(data)
    ranking = calculate_scores(data, target_date=target_date)
    if save:
        save_ranking(ranking, target_date)
    return ranking
