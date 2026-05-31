"""Small shared utilities."""

from __future__ import annotations

import csv
import logging
import logging.config
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import yaml

from .config import (
    BACKTEST_REPORT_DIR,
    CACHE_DIR,
    CHART_DIR,
    CONFIG_DIR,
    DAILY_REPORT_DIR,
    DATA_DIR,
    LOG_DIR,
    PROCESSED_DATA_DIR,
    PROJECT_ROOT,
    RAW_DATA_DIR,
    SNAPSHOT_DIR,
    copy_readme_spec_if_missing,
    write_default_settings,
)
from .constants import ERROR_LOG_FIELDS, RISK_LOG_FIELDS, TRADE_LOG_FIELDS, WATCH_LOG_FIELDS


def today_str() -> str:
    return date.today().isoformat()


def parse_date(value: str | datetime | date | None) -> str:
    if value is None:
        return today_str()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date().isoformat()


def ensure_directories() -> None:
    for path in [
        CONFIG_DIR,
        DATA_DIR,
        RAW_DATA_DIR,
        PROCESSED_DATA_DIR,
        CACHE_DIR,
        SNAPSHOT_DIR,
        LOG_DIR,
        DAILY_REPORT_DIR,
        BACKTEST_REPORT_DIR,
        CHART_DIR,
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "tests",
    ]:
        path.mkdir(parents=True, exist_ok=True)


def ensure_csv(path: Path, fieldnames: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size == 0:
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(fieldnames))
            writer.writeheader()


def ensure_log_files() -> None:
    ensure_csv(LOG_DIR / "trade_log.csv", TRADE_LOG_FIELDS)
    ensure_csv(LOG_DIR / "watch_log.csv", WATCH_LOG_FIELDS)
    ensure_csv(LOG_DIR / "risk_log.csv", RISK_LOG_FIELDS)
    ensure_csv(LOG_DIR / "error_log.csv", ERROR_LOG_FIELDS)
    (LOG_DIR / "app.log").touch(exist_ok=True)


def setup_logging() -> None:
    ensure_directories()
    config_path = CONFIG_DIR / "logging.yaml"
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as fh:
            config = yaml.safe_load(fh) or {}
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def init_project() -> None:
    ensure_directories()
    write_default_settings()
    from .uzi import write_default_uzi_config

    write_default_uzi_config()
    ensure_log_files()
    copy_readme_spec_if_missing()


def append_csv_row(path: Path, fieldnames: list[str], row: dict) -> None:
    ensure_csv(path, fieldnames)
    safe_row = {field: row.get(field, "") for field in fieldnames}
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writerow(safe_row)


def log_error(module: str, symbol: str, error_type: str, message: str) -> None:
    append_csv_row(
        LOG_DIR / "error_log.csv",
        ERROR_LOG_FIELDS,
        {
            "date": today_str(),
            "module": module,
            "symbol": symbol,
            "error_type": error_type,
            "message": str(message),
        },
    )


def log_risk(date_value: str, risk_type: str, level: str, symbol: str, message: str, action: str) -> None:
    append_csv_row(
        LOG_DIR / "risk_log.csv",
        RISK_LOG_FIELDS,
        {
            "date": date_value,
            "risk_type": risk_type,
            "level": level,
            "symbol": symbol,
            "message": message,
            "action_required": action,
        },
    )


def round_price(price: float, tick: float = 0.001) -> float:
    return round(round(float(price) / tick) * tick, 3)
