"""Data normalization and validation."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .constants import STANDARD_COLUMNS
from .utils import log_error

COLUMN_MAP = {
    "日期": "date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
    "振幅": "amplitude",
    "涨跌幅": "pct_change",
    "涨跌额": "change",
    "换手率": "turnover",
}


@dataclass
class ValidationIssue:
    symbol: str
    error_type: str
    message: str


def _normalize_ratio(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if values.dropna().abs().gt(1).any():
        values = values / 100.0
    return values


def clean_etf_history(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    cleaned = df.rename(columns=COLUMN_MAP).copy()
    if "date" not in cleaned.columns:
        raise ValueError("missing date column")
    cleaned["date"] = pd.to_datetime(cleaned["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    cleaned["symbol"] = str(symbol).zfill(6)
    for col in ["open", "high", "low", "close", "volume", "amount", "change"]:
        if col not in cleaned.columns:
            cleaned[col] = pd.NA
        cleaned[col] = pd.to_numeric(cleaned[col], errors="coerce")
    for col in ["amplitude", "pct_change", "turnover"]:
        if col not in cleaned.columns:
            cleaned[col] = 0.0
        cleaned[col] = _normalize_ratio(cleaned[col])
    cleaned = cleaned.dropna(subset=["date"]).sort_values("date")
    cleaned = cleaned.drop_duplicates(subset=["date"], keep="last")
    return cleaned[STANDARD_COLUMNS].reset_index(drop=True)


def validate_clean_data(df: pd.DataFrame, symbol: str, min_history_days: int = 120) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if df.empty:
        issues.append(ValidationIssue(symbol, "empty_data", "no rows after cleaning"))
    if df["date"].duplicated().any():
        issues.append(ValidationIssue(symbol, "duplicate_date", "duplicate dates found"))
    if not df["date"].is_monotonic_increasing:
        issues.append(ValidationIssue(symbol, "date_order", "dates are not ascending"))
    if df[["open", "high", "low", "close"]].isna().any().any():
        issues.append(ValidationIssue(symbol, "missing_ohlc", "open/high/low/close has null values"))
    if (pd.to_numeric(df["close"], errors="coerce") <= 0).any():
        issues.append(ValidationIssue(symbol, "invalid_close", "close is less than or equal to zero"))
    if df["amount"].isna().any():
        issues.append(ValidationIssue(symbol, "missing_amount", "amount has null values"))
    if len(df) < min_history_days:
        issues.append(ValidationIssue(symbol, "insufficient_history", f"history rows {len(df)} < {min_history_days}"))
    for issue in issues:
        log_error("data_cleaner", symbol, issue.error_type, issue.message)
    return issues
