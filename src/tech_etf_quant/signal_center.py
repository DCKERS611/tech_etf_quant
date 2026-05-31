"""Centralized explainable signal table for the v2 workbench."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .config import SIGNAL_REPORT_DIR, Settings, load_settings
from .data_loader import ensure_sample_data, latest_available_date, load_processed_data
from .portfolio import Portfolio
from .risk import evaluate_trade_permission
from .scoring import calculate_scores, save_ranking
from .strategy_registry import StrategyCandidate, pick_best_candidate

SIGNAL_CENTER_COLUMNS = [
    "generated_at",
    "date",
    "signal_rank",
    "symbol",
    "name",
    "group",
    "rank_all",
    "rank_group",
    "score",
    "score_band",
    "trend_state",
    "strategy",
    "signal_type",
    "position_type",
    "suggested_amount",
    "confidence",
    "risk_state",
    "risk_permission",
    "reason",
    "invalid_condition",
    "explain",
    "data_quality",
]


def _score_band(score: float) -> str:
    if score >= 0.18:
        return "S"
    if score >= 0.10:
        return "A"
    if score >= 0.04:
        return "B"
    if score >= 0:
        return "C"
    return "D"


def _trend_state(row: pd.Series | dict) -> str:
    if bool(row.get("trend_ok", False)):
        if float(row.get("volume_boost", 1) or 1) >= 1.5:
            return "趋势健康/放量"
        return "趋势健康"
    if float(row.get("close", 0) or 0) < float(row.get("ma60", 0) or 0):
        return "MA60下方"
    return "震荡观察"


def _risk_permission(candidate: StrategyCandidate) -> str:
    signal_type = candidate.signal.signal_type
    if signal_type == "HOLD":
        return "观察"
    if candidate.signal.position_type == "TEST":
        return "只允许测试仓"
    return "允许主仓"


def _explain(row: pd.Series | dict, candidate: StrategyCandidate) -> str:
    parts = [
        candidate.explanation,
        f"全市场排名 {int(float(row.get('rank_all', 0) or 0))}",
        f"组内排名 {int(float(row.get('rank_group', 0) or 0))}",
        f"R20 {float(row.get('r20', 0) or 0) * 100:.2f}%",
        f"R60 {float(row.get('r60', 0) or 0) * 100:.2f}%",
        f"放量 {float(row.get('volume_boost', 0) or 0):.2f}x",
    ]
    return "；".join(parts)


def _data_quality(row: pd.Series | dict) -> str:
    close = float(row.get("close", 0) or 0)
    ma20 = float(row.get("ma20", 0) or 0)
    ma60 = float(row.get("ma60", 0) or 0)
    amount_ok = float(row.get("volume_boost", 0) or 0) > 0
    if close > 0 and ma20 > 0 and ma60 > 0 and amount_ok:
        return "OK"
    return "CHECK"


def build_signal_center(
    target_date: str | None = None,
    ranking: pd.DataFrame | None = None,
    portfolio: Portfolio | None = None,
    settings: Settings | None = None,
    save: bool = True,
) -> pd.DataFrame:
    settings = settings or load_settings()
    portfolio = portfolio or Portfolio(cash=float(settings.get("account.initial_cash", 8000)))
    if ranking is None:
        data = load_processed_data()
        if not data:
            data = ensure_sample_data()
        target_date = target_date or latest_available_date(data)
        ranking = calculate_scores(data, target_date=target_date, settings=settings)
        if target_date:
            save_ranking(ranking, target_date)
    if ranking.empty:
        return pd.DataFrame(columns=SIGNAL_CENTER_COLUMNS)
    target_date = target_date or str(ranking["date"].max())
    generated_at = datetime.now().isoformat(timespec="seconds")
    rows: list[dict[str, Any]] = []
    tradable = ranking[ranking["group"] != "benchmark"].sort_values(["rank_all", "rank_group"])
    for _, row in tradable.iterrows():
        risk = evaluate_trade_permission(
            portfolio,
            pct_change=float(row.get("pct_change", 0) or 0),
            high_open_gap=0.0,
            watch_time="14:35",
            settings=settings,
        )
        candidate = pick_best_candidate(row, risk, settings=settings)
        signal = candidate.signal
        rows.append(
            {
                "generated_at": generated_at,
                "date": target_date,
                "signal_rank": 0,
                "symbol": row["symbol"],
                "name": row["name"],
                "group": row["group"],
                "rank_all": int(row["rank_all"]),
                "rank_group": int(row["rank_group"]),
                "score": float(row["score"]),
                "score_band": _score_band(float(row["score"])),
                "trend_state": _trend_state(row),
                "strategy": candidate.label,
                "signal_type": signal.signal_type,
                "position_type": signal.position_type,
                "suggested_amount": signal.suggested_amount,
                "confidence": candidate.confidence,
                "risk_state": risk.risk_state,
                "risk_permission": _risk_permission(candidate),
                "reason": signal.reason,
                "invalid_condition": signal.invalid_condition,
                "explain": _explain(row, candidate),
                "data_quality": _data_quality(row),
            }
        )
    center = pd.DataFrame(rows)
    if center.empty:
        return pd.DataFrame(columns=SIGNAL_CENTER_COLUMNS)
    center = center.sort_values(["confidence", "score", "rank_all"], ascending=[False, False, True]).reset_index(drop=True)
    center["signal_rank"] = range(1, len(center) + 1)
    center = center[SIGNAL_CENTER_COLUMNS]
    if save:
        save_signal_center(center, target_date)
    return center


def save_signal_center(center: pd.DataFrame, target_date: str | None = None, output_dir: Path | None = None) -> dict[str, Path]:
    output_dir = output_dir or SIGNAL_REPORT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    target_date = target_date or (str(center["date"].max()) if not center.empty else "unknown")
    csv_path = output_dir / f"{target_date}_signal_center.csv"
    json_path = output_dir / f"{target_date}_signal_center.json"
    center.to_csv(csv_path, index=False, encoding="utf-8")
    payload = center.to_dict("records")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"csv": csv_path, "json": json_path}


def latest_signal_center(target_date: str | None = None) -> pd.DataFrame:
    if target_date is None:
        files = sorted(SIGNAL_REPORT_DIR.glob("*_signal_center.csv"))
        path = files[-1] if files else None
    else:
        path = SIGNAL_REPORT_DIR / f"{target_date}_signal_center.csv"
    if path is None or not path.exists():
        return pd.DataFrame(columns=SIGNAL_CENTER_COLUMNS)
    return pd.read_csv(path, dtype={"symbol": str})


def summarize_signal_center(center: pd.DataFrame) -> dict[str, Any]:
    if center.empty:
        return {"count": 0, "actionable": 0, "top": None, "avg_confidence": 0.0}
    actionable = center[center["signal_type"] != "HOLD"]
    top = center.iloc[0].to_dict()
    return {
        "count": int(len(center)),
        "actionable": int(len(actionable)),
        "top": top,
        "avg_confidence": float(center["confidence"].mean()),
        "by_signal": center["signal_type"].value_counts().to_dict(),
    }


def signal_record_to_dict(record: StrategyCandidate) -> dict[str, Any]:
    return {
        "rule_name": record.rule_name,
        "label": record.label,
        "priority": record.priority,
        "matched": record.matched,
        "confidence": record.confidence,
        "explanation": record.explanation,
        "signal": asdict(record.signal),
    }
