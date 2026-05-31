"""Intraday watch decisions.

Realtime data is pulled automatically first. Local realtime cache is used as the
fallback. Manual CSV remains available only as the last fallback path.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import SNAPSHOT_DIR, load_settings
from .constants import WATCH_LOG_FIELDS
from .realtime import read_realtime_cache, refresh_realtime
from .utils import LOG_DIR, append_csv_row

SNAPSHOT_COLUMNS = [
    "date",
    "time",
    "symbol",
    "price",
    "pct_change",
    "amount",
    "volume",
    "high",
    "low",
    "open",
    "prev_close",
    "note",
]

AUTO_WATCH_TIMES = ["09:35", "10:35", "11:30", "13:30", "14:35"]


def snapshot_template(path: Path | None = None) -> Path:
    path = path or (SNAPSHOT_DIR / "input_snapshot.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        pd.DataFrame(columns=SNAPSHOT_COLUMNS).to_csv(path, index=False, encoding="utf-8")
    return path


def read_input_snapshot(path: Path | None = None) -> pd.DataFrame:
    path = path or (SNAPSHOT_DIR / "input_snapshot.csv")
    if not path.exists():
        snapshot_template(path)
        return pd.DataFrame(columns=SNAPSHOT_COLUMNS)
    df = pd.read_csv(path, dtype={"symbol": str})
    for col in SNAPSHOT_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["symbol"] = df["symbol"].astype(str).str.zfill(6)
    for col in ["price", "pct_change", "amount", "volume", "high", "low", "open", "prev_close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df[SNAPSHOT_COLUMNS]


def _to_snapshot_columns(df: pd.DataFrame, source: str = "manual_csv") -> pd.DataFrame:
    out = df.copy()
    for col in SNAPSHOT_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    if "source" not in out.columns:
        out["source"] = source
    for col in ["price", "pct_change", "amount", "volume", "high", "low", "open", "prev_close"]:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    out["symbol"] = out["symbol"].astype(str).str.zfill(6)
    out["note"] = out["note"].fillna("").astype(str)
    return out


def evaluate_snapshot_row(row: pd.Series, watch_time: str) -> tuple[str, str]:
    pct = float(row.get("pct_change", 0) or 0)
    open_price = float(row.get("open", 0) or 0)
    prev_close = float(row.get("prev_close", 0) or 0)
    price = float(row.get("price", 0) or 0)
    high = float(row.get("high", 0) or 0)
    high_open_gap = open_price / prev_close - 1 if prev_close > 0 else 0.0
    if watch_time == "09:35":
        if high_open_gap > 0.02:
            return "HIGH_OPEN_BLOCK", "集合竞价后高开超过2%，禁止开盘追入"
        if pct > 0.04:
            return "WATCH", "9:35仅确认开盘强弱，涨幅较高时不追主仓"
        return "OPEN_WATCH", "集合竞价后观察开盘质量，主仓等待后续确认"
    if watch_time in {"10:30", "10:35"}:
        if pct > 0.04:
            return "CHASE_BLOCK", "涨幅超过4%，10:35禁止主仓追入，仅观察或测试仓"
        if high_open_gap > 0.02:
            return "HIGH_OPEN_BLOCK", "高开超过2%，禁止开盘追入"
        return "WATCH", "10:35只观察或测试仓，等待14:35确认"
    if watch_time == "11:30":
        if high > 0 and price < high * 0.985:
            return "PULLBACK_ALERT", "午休出现冲高回落，下午计划降级"
        return "MIDDAY_OK", "午休强势保持，下午继续观察"
    if watch_time in {"13:00", "13:30"}:
        if high > 0 and price < high * 0.98:
            return "CANCEL_CHASE", "午市开盘快速回落，取消追涨计划"
        return "CONFIRM", "13:30强势延续确认，等待14:35执行点"
    if watch_time in {"14:30", "14:35"}:
        if pct > 0.06:
            return "ONLY_TEST", "涨幅超过6%，禁止新开主仓，只允许测试仓"
        return "ACTION_ALLOWED", "14:35可按排名、趋势和风控执行计划"
    return "WATCH", "非标准观察时间，记录快照并继续观察"


def save_snapshot(df: pd.DataFrame, target_date: str, watch_time: str) -> Path:
    out = df.copy()
    out["date"] = target_date
    out["time"] = watch_time
    path = SNAPSHOT_DIR / f"{target_date}_snapshot.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        old = pd.read_csv(path, dtype={"symbol": str})
        out = pd.concat([old, out], ignore_index=True)
        out = out.drop_duplicates(subset=["date", "time", "symbol"], keep="last")
    out.to_csv(path, index=False, encoding="utf-8")
    return path


def load_watch_snapshot(
    target_date: str,
    watch_time: str,
    snapshot_path: Path | None = None,
    source: str = "auto",
) -> tuple[pd.DataFrame, str]:
    if source == "manual":
        manual = read_input_snapshot(snapshot_path)
        return _to_snapshot_columns(manual, "manual_csv"), "manual_csv"

    auto = refresh_realtime(target_date, watch_time)
    if not auto.empty:
        return _to_snapshot_columns(auto, "akshare_realtime"), "akshare_realtime"

    cache = read_realtime_cache(target_date, watch_time)
    if not cache.empty:
        return _to_snapshot_columns(cache, "local_cache"), "local_cache"

    manual = read_input_snapshot(snapshot_path)
    if not manual.empty:
        return _to_snapshot_columns(manual, "manual_csv"), "manual_csv"
    return pd.DataFrame(columns=SNAPSHOT_COLUMNS + ["source"]), "manual_csv"


def run_watch(
    target_date: str,
    watch_time: str,
    snapshot_path: Path | None = None,
    source: str = "auto",
) -> pd.DataFrame:
    df, data_source = load_watch_snapshot(target_date, watch_time, snapshot_path, source)
    if df.empty:
        snapshot_template(snapshot_path)
        return pd.DataFrame(columns=WATCH_LOG_FIELDS)
    df["date"] = target_date
    df["time"] = watch_time
    decisions: list[dict] = []
    for _, row in df.iterrows():
        status, decision = evaluate_snapshot_row(row, watch_time)
        record = {
            "date": target_date,
            "time": watch_time,
            "symbol": row["symbol"],
            "price": row["price"],
            "pct_change": row["pct_change"],
            "amount": row["amount"],
            "status": status,
            "watch_decision": decision,
            "note": f"{data_source}; {row.get('note', '')}".strip("; "),
        }
        append_csv_row(LOG_DIR / "watch_log.csv", WATCH_LOG_FIELDS, record)
        decisions.append({**record, "source": data_source})
    save_snapshot(df, target_date, watch_time)
    return pd.DataFrame(decisions)


def configured_watch_times() -> list[str]:
    settings = load_settings()
    return list(settings.get("watch.watch_times", AUTO_WATCH_TIMES))
