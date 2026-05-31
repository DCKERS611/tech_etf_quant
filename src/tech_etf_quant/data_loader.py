"""ETF historical data download, cache and local fallback data."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .config import PROCESSED_DATA_DIR, RAW_DATA_DIR, load_etf_pool
from .data_cleaner import clean_etf_history, validate_clean_data
from .indicators import add_indicators
from .utils import log_error

logger = logging.getLogger(__name__)


def _ak_date(value: str | date | None) -> str:
    if value is None:
        return date.today().strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    return str(value).replace("-", "")[:8]


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype={"symbol": str})


def fetch_etf_history(symbol: str, start_date: str = "20200101", end_date: str | None = None) -> pd.DataFrame:
    """Fetch ETF daily history from AKShare."""

    try:
        import akshare as ak

        logger.info("Downloading ETF %s from %s to %s", symbol, start_date, end_date or "today")
        return ak.fund_etf_hist_em(
            symbol=str(symbol).zfill(6),
            period="daily",
            start_date=_ak_date(start_date),
            end_date=_ak_date(end_date),
            adjust="qfq",
        )
    except Exception as exc:  # pragma: no cover - depends on external data source
        log_error("data_loader", symbol, "download_failed", str(exc))
        logger.warning("AKShare download failed for %s: %s", symbol, exc)
        return pd.DataFrame()


def generate_synthetic_history(
    symbol: str,
    name: str = "",
    start_date: str = "2021-01-01",
    end_date: str | None = None,
) -> pd.DataFrame:
    """Create deterministic daily sample data so the local system always runs."""

    end_date = end_date or date.today().isoformat()
    dates = pd.bdate_range(start=start_date, end=end_date)
    if len(dates) == 0:
        dates = pd.bdate_range(end=date.today(), periods=260)
    seed = int(str(symbol).zfill(6)[-6:]) % (2**32 - 1)
    rng = np.random.default_rng(seed)
    base = 0.85 + (seed % 60) / 100
    drift = 0.00025 + ((seed % 13) - 6) / 100000
    noise = rng.normal(drift, 0.012, len(dates))
    cycle = np.sin(np.linspace(0, 8 * np.pi, len(dates))) * 0.002
    returns = noise + cycle
    close = base * np.cumprod(1 + returns)
    open_ = close * (1 + rng.normal(0, 0.004, len(dates)))
    high = np.maximum(open_, close) * (1 + rng.uniform(0.001, 0.015, len(dates)))
    low = np.minimum(open_, close) * (1 - rng.uniform(0.001, 0.015, len(dates)))
    volume = rng.integers(8_000_000, 60_000_000, len(dates)).astype(float)
    amount = volume * close
    pct_change = pd.Series(close).pct_change().fillna(0).to_numpy()
    change = np.diff(np.r_[close[0], close])
    amplitude = (high - low) / np.maximum(np.r_[close[0], close[:-1]], 0.001)
    turnover = rng.uniform(0.002, 0.05, len(dates))
    df = pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "symbol": str(symbol).zfill(6),
            "open": np.round(open_, 3),
            "high": np.round(high, 3),
            "low": np.round(low, 3),
            "close": np.round(close, 3),
            "volume": volume,
            "amount": np.round(amount, 2),
            "amplitude": amplitude,
            "pct_change": pct_change,
            "change": np.round(change, 3),
            "turnover": turnover,
        }
    )
    logger.info("Generated sample data for %s %s with %s rows", symbol, name, len(df))
    return df


def update_symbol_data(
    symbol: str,
    name: str = "",
    start_date: str = "20200101",
    end_date: str | None = None,
    min_history_days: int = 120,
    use_fallback: bool = True,
) -> pd.DataFrame:
    """Download or incrementally update one ETF, then save raw and processed CSV."""

    symbol = str(symbol).zfill(6)
    raw_path = RAW_DATA_DIR / f"{symbol}.csv"
    processed_path = PROCESSED_DATA_DIR / f"{symbol}.csv"
    existing = _read_csv(raw_path)
    fetch_start = start_date
    if not existing.empty and "date" in existing.columns:
        last_date = pd.to_datetime(existing["date"]).max()
        if pd.notna(last_date):
            fetch_start = (last_date + timedelta(days=1)).strftime("%Y%m%d")
    downloaded = fetch_etf_history(symbol, fetch_start, end_date)
    pieces = []
    if not existing.empty:
        pieces.append(existing)
    if downloaded is not None and not downloaded.empty:
        pieces.append(clean_etf_history(downloaded, symbol))
    if pieces:
        raw = pd.concat(pieces, ignore_index=True)
        raw = clean_etf_history(raw, symbol)
    elif use_fallback:
        raw = generate_synthetic_history(symbol, name, "2021-01-01", end_date)
        log_error("data_loader", symbol, "fallback_data", "used deterministic local sample data")
    else:
        raw = pd.DataFrame()
    if raw.empty:
        log_error("data_loader", symbol, "no_data", "no data available after update")
        return raw
    raw = raw.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    processed_path.parent.mkdir(parents=True, exist_ok=True)
    raw.to_csv(raw_path, index=False, encoding="utf-8")
    processed = add_indicators(raw)
    validate_clean_data(processed, symbol, min_history_days=min_history_days)
    processed.to_csv(processed_path, index=False, encoding="utf-8")
    return processed


def update_all_data(
    start_date: str = "20200101",
    end_date: str | None = None,
    enabled_only: bool = True,
    use_fallback: bool = True,
) -> dict[str, pd.DataFrame]:
    pool = load_etf_pool(enabled_only=enabled_only)
    out: dict[str, pd.DataFrame] = {}
    for row in pool.itertuples(index=False):
        try:
            out[row.symbol] = update_symbol_data(
                row.symbol,
                getattr(row, "name", ""),
                start_date=start_date,
                end_date=end_date,
                use_fallback=use_fallback,
            )
        except Exception as exc:
            log_error("data_loader", row.symbol, "update_symbol_failed", str(exc))
    return out


def ensure_sample_data(
    start_date: str = "2021-01-01",
    end_date: str | None = None,
    overwrite: bool = False,
) -> dict[str, pd.DataFrame]:
    pool = load_etf_pool(enabled_only=True)
    out: dict[str, pd.DataFrame] = {}
    for row in pool.itertuples(index=False):
        path = PROCESSED_DATA_DIR / f"{row.symbol}.csv"
        if path.exists() and not overwrite:
            df = pd.read_csv(path, dtype={"symbol": str})
        else:
            df = generate_synthetic_history(row.symbol, row.name, start_date, end_date)
            (RAW_DATA_DIR / f"{row.symbol}.csv").parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(RAW_DATA_DIR / f"{row.symbol}.csv", index=False, encoding="utf-8")
            df = add_indicators(df)
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(path, index=False, encoding="utf-8")
        out[row.symbol] = df
    return out


def load_processed_data(symbols: list[str] | None = None, with_indicators: bool = True) -> dict[str, pd.DataFrame]:
    if symbols is None:
        files = sorted(PROCESSED_DATA_DIR.glob("*.csv"))
    else:
        files = [PROCESSED_DATA_DIR / f"{str(symbol).zfill(6)}.csv" for symbol in symbols]
    out: dict[str, pd.DataFrame] = {}
    for path in files:
        if not path.exists():
            continue
        df = pd.read_csv(path, dtype={"symbol": str})
        if with_indicators and "ma20" not in df.columns:
            df = add_indicators(df)
        out[path.stem.zfill(6)] = df
    return out


def latest_available_date(data_by_symbol: dict[str, pd.DataFrame]) -> str | None:
    dates: list[str] = []
    for df in data_by_symbol.values():
        if not df.empty and "date" in df:
            dates.append(str(df["date"].dropna().max()))
    return max(dates) if dates else None
