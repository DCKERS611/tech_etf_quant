"""Daily indicator calculation."""

from __future__ import annotations

import pandas as pd


def _add_single_symbol_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values("date").copy()
    close = pd.to_numeric(out["close"], errors="coerce")
    amount = pd.to_numeric(out["amount"], errors="coerce")
    out["ma20"] = close.rolling(20, min_periods=20).mean()
    out["ma60"] = close.rolling(60, min_periods=60).mean()
    out["r5"] = close / close.shift(5) - 1
    out["r20"] = close / close.shift(20) - 1
    out["r60"] = close / close.shift(60) - 1
    out["daily_return"] = close.pct_change()
    out["vol20"] = out["daily_return"].rolling(20, min_periods=20).std()
    out["amount_ma20"] = amount.rolling(20, min_periods=20).mean()
    out["volume_boost"] = amount / out["amount_ma20"]
    out["drawdown_from_20d_high"] = close / close.rolling(20, min_periods=20).max() - 1
    out["drawdown_from_60d_high"] = close / close.rolling(60, min_periods=60).max() - 1
    out["is_above_ma20"] = close > out["ma20"]
    out["is_above_ma60"] = close > out["ma60"]
    out["is_ma20_above_ma60"] = out["ma20"] > out["ma60"]
    out["trend_ok"] = (
        out["is_above_ma20"] & out["is_ma20_above_ma60"] & (out["r20"] > 0) & (out["r60"] > 0)
    )
    return out


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add rolling daily indicators without using future data."""

    if df.empty:
        return df.copy()
    if "symbol" in df.columns and df["symbol"].nunique() > 1:
        pieces = [_add_single_symbol_indicators(part) for _, part in df.groupby("symbol", sort=False)]
        return pd.concat(pieces, ignore_index=True).sort_values(["symbol", "date"]).reset_index(drop=True)
    return _add_single_symbol_indicators(df).reset_index(drop=True)
