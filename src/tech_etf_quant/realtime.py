"""Intraday realtime ETF data with cache fallback support."""

from __future__ import annotations

import logging
import contextlib
import io
from datetime import datetime
from pathlib import Path

import pandas as pd

from .config import CACHE_DIR, SNAPSHOT_DIR, load_etf_pool, normalize_symbol
from .utils import log_error

logger = logging.getLogger(__name__)

REALTIME_CACHE_PATH = CACHE_DIR / "realtime_etf_spot.csv"

REALTIME_COLUMNS = [
    "date",
    "time",
    "symbol",
    "name",
    "price",
    "pct_change",
    "amount",
    "volume",
    "high",
    "low",
    "open",
    "prev_close",
    "source",
    "source_time",
    "note",
]

SPOT_COLUMN_MAP = {
    "代码": "symbol",
    "名称": "name",
    "最新价": "price",
    "涨跌幅": "pct_change",
    "成交额": "amount",
    "成交量": "volume",
    "最高价": "high",
    "最低价": "low",
    "开盘价": "open",
    "昨收": "prev_close",
    "数据日期": "date",
    "更新时间": "source_time",
}


def _snapshot_path(target_date: str, watch_time: str) -> Path:
    safe_time = watch_time.replace(":", "")
    return SNAPSHOT_DIR / f"{target_date}_realtime_{safe_time}.csv"


def _as_ratio(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").fillna(0.0)
    if values.abs().gt(1).any():
        values = values / 100.0
    return values


def normalize_realtime_spot(df: pd.DataFrame, target_date: str, watch_time: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=REALTIME_COLUMNS)
    pool = load_etf_pool(enabled_only=True)
    meta = pool.set_index("symbol").to_dict("index")
    out = df.rename(columns=SPOT_COLUMN_MAP).copy()
    if "symbol" not in out.columns:
        return pd.DataFrame(columns=REALTIME_COLUMNS)
    out["symbol"] = out["symbol"].map(normalize_symbol)
    out = out[out["symbol"].isin(meta)].copy()
    if out.empty:
        return pd.DataFrame(columns=REALTIME_COLUMNS)
    out["date"] = target_date
    out["time"] = watch_time
    out["name"] = out.apply(lambda row: row.get("name") or meta[row["symbol"]].get("name", ""), axis=1)
    for col in ["price", "amount", "volume", "high", "low", "open", "prev_close"]:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    if "pct_change" not in out.columns:
        out["pct_change"] = 0.0
    out["pct_change"] = _as_ratio(out["pct_change"])
    if "source_time" not in out.columns:
        out["source_time"] = datetime.now().isoformat(timespec="seconds")
    out["source"] = "akshare_realtime"
    out["note"] = out["source_time"].map(lambda value: f"auto realtime source_time={value}")
    return out[REALTIME_COLUMNS].sort_values("symbol").reset_index(drop=True)


def fetch_realtime_spot(target_date: str, watch_time: str) -> pd.DataFrame:
    """Fetch realtime ETF spot data from AKShare and normalize it for watch rules."""

    try:
        import akshare as ak

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            raw = ak.fund_etf_spot_em()
        normalized = normalize_realtime_spot(raw, target_date, watch_time)
        if normalized.empty:
            log_error("realtime", "", "empty_realtime", "AKShare realtime ETF spot returned no configured symbols")
        return normalized
    except Exception as exc:  # pragma: no cover - external data source
        log_error("realtime", "", "realtime_fetch_failed", str(exc))
        logger.warning("Realtime fetch failed: %s", exc)
        return pd.DataFrame(columns=REALTIME_COLUMNS)


def save_realtime_cache(df: pd.DataFrame, target_date: str, watch_time: str) -> None:
    if df.empty:
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(REALTIME_CACHE_PATH, index=False, encoding="utf-8")
    df.to_csv(_snapshot_path(target_date, watch_time), index=False, encoding="utf-8")


def read_realtime_cache(target_date: str | None = None, watch_time: str | None = None) -> pd.DataFrame:
    candidates: list[Path] = []
    if target_date and watch_time:
        candidates.append(_snapshot_path(target_date, watch_time))
    candidates.append(REALTIME_CACHE_PATH)
    for path in candidates:
        if path.exists():
            df = pd.read_csv(path, dtype={"symbol": str})
            for col in REALTIME_COLUMNS:
                if col not in df.columns:
                    df[col] = ""
            df["source"] = "local_cache"
            df["note"] = df["note"].fillna("").astype(str) + " cache fallback"
            return df[REALTIME_COLUMNS]
    return pd.DataFrame(columns=REALTIME_COLUMNS)


def refresh_realtime(target_date: str, watch_time: str) -> pd.DataFrame:
    df = fetch_realtime_spot(target_date, watch_time)
    if not df.empty:
        save_realtime_cache(df, target_date, watch_time)
    return df
