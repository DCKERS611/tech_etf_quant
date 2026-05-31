"""Configuration helpers."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
CACHE_DIR = DATA_DIR / "cache"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
LOG_DIR = PROJECT_ROOT / "logs"
REPORT_DIR = PROJECT_ROOT / "reports"
DAILY_REPORT_DIR = REPORT_DIR / "daily"
BACKTEST_REPORT_DIR = REPORT_DIR / "backtest"
CHART_DIR = REPORT_DIR / "charts"


DEFAULT_SETTINGS: dict[str, Any] = {
    "account": {
        "initial_cash": 8000,
        "max_account_loss_ratio": 0.08,
        "test_position_amount": 1000,
        "light_position_amount": 2000,
        "standard_position_min": 3000,
        "standard_position_max": 5000,
        "max_position_ratio": 0.80,
        "min_cash_reserve": 1000,
    },
    "trading": {
        "commission_rate": 0.00001,
        "slippage_rate": 0.0003,
        "lot_size": 100,
        "price_tick": 0.001,
        "execute_price": "next_open",
        "allow_short": False,
        "allow_margin": False,
        "allow_t0": False,
    },
    "risk": {
        "test_stop_loss_ratio": 0.05,
        "main_stop_loss_ratio": 0.06,
        "account_max_loss_ratio": 0.08,
        "chase_limit_normal": 0.04,
        "chase_limit_hard": 0.06,
        "high_open_limit": 0.02,
        "consecutive_loss_limit_1": 2,
        "consecutive_loss_limit_2": 3,
        "main_trade_cooldown_days": 10,
    },
    "indicators": {
        "ma_short": 20,
        "ma_long": 60,
        "r_short": 5,
        "r_mid": 20,
        "r_long": 60,
        "vol_window": 20,
        "amount_window": 20,
    },
    "filters": {"min_avg_amount": 30000000, "min_history_days": 120},
    "watch": {
        "data_source_priority": ["akshare_realtime", "local_cache", "manual_csv"],
        "watch_times": ["09:35", "10:35", "11:30", "13:30", "14:35"],
    },
    "report": {"benchmark_symbols": ["588000", "159915", "510300"]},
}


@dataclass(frozen=True)
class Settings:
    values: dict[str, Any]

    def section(self, name: str) -> dict[str, Any]:
        return dict(self.values.get(name, {}))

    def get(self, dotted_key: str, default: Any = None) -> Any:
        cur: Any = self.values
        for part in dotted_key.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_settings(path: Path | None = None) -> Settings:
    path = path or CONFIG_DIR / "settings.yaml"
    if not path.exists():
        return Settings(DEFAULT_SETTINGS)
    with path.open("r", encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh) or {}
    return Settings(deep_merge(DEFAULT_SETTINGS, loaded))


def write_default_settings(path: Path | None = None) -> Path:
    path = path or CONFIG_DIR / "settings.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(DEFAULT_SETTINGS, fh, allow_unicode=True, sort_keys=False)
    return path


def normalize_symbol(symbol: str | int) -> str:
    text = str(symbol).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6)


def load_etf_pool(path: Path | None = None, enabled_only: bool = True) -> pd.DataFrame:
    path = path or CONFIG_DIR / "etf_pool.csv"
    if not path.exists():
        raise FileNotFoundError(f"ETF pool not found: {path}")
    df = pd.read_csv(path, dtype={"symbol": str})
    df["symbol"] = df["symbol"].map(normalize_symbol)
    if "enabled" in df.columns:
        df["enabled"] = df["enabled"].astype(str).str.lower().isin(["true", "1", "yes", "y"])
        if enabled_only:
            df = df[df["enabled"]].copy()
    return df.reset_index(drop=True)


def copy_readme_spec_if_missing() -> None:
    source = PROJECT_ROOT / "README_tech_etf_quant_system_full_spec_v1.md"
    target = PROJECT_ROOT / "README_SPEC.md"
    if source.exists() and not target.exists():
        shutil.copyfile(source, target)
