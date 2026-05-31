"""Refresh scheduler helpers for local and Streamlit-driven operation."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, time as dt_time
from pathlib import Path

import pandas as pd

from .config import SCHEDULE_REPORT_DIR, load_settings
from .data_loader import update_all_data
from .watch import configured_watch_times, run_watch


@dataclass(frozen=True)
class RefreshSlot:
    date: str
    time: str
    status: str
    source: str
    rows: int
    message: str


def _parse_hhmm(value: str) -> dt_time:
    return datetime.strptime(value, "%H:%M").time()


def schedule_path(target_date: str) -> Path:
    return SCHEDULE_REPORT_DIR / f"{target_date}_refresh_status.csv"


def load_refresh_status(target_date: str) -> pd.DataFrame:
    path = schedule_path(target_date)
    if not path.exists():
        return pd.DataFrame(columns=["date", "time", "status", "source", "rows", "message"])
    return pd.read_csv(path, dtype={"time": str})


def save_refresh_status(target_date: str, slots: list[RefreshSlot]) -> Path:
    SCHEDULE_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_refresh_status(target_date)
    incoming = pd.DataFrame([asdict(slot) for slot in slots])
    if not existing.empty:
        incoming = pd.concat([existing, incoming], ignore_index=True)
        incoming = incoming.drop_duplicates(subset=["date", "time"], keep="last")
    path = schedule_path(target_date)
    incoming.sort_values(["date", "time"]).to_csv(path, index=False, encoding="utf-8")
    return path


def refresh_plan(now: datetime | None = None, target_date: str | None = None) -> pd.DataFrame:
    now = now or datetime.now()
    target_date = target_date or now.date().isoformat()
    status = load_refresh_status(target_date)
    completed = set(status[status["status"] == "done"]["time"].astype(str)) if not status.empty else set()
    rows = []
    for item in configured_watch_times():
        slot_time = _parse_hhmm(item)
        if item in completed:
            state = "done"
        elif now.time() >= slot_time:
            state = "due"
        else:
            state = "pending"
        rows.append({"date": target_date, "time": item, "state": state})
    return pd.DataFrame(rows)


def next_refresh_time(now: datetime | None = None) -> str:
    now = now or datetime.now()
    for item in configured_watch_times():
        if now.time() < _parse_hhmm(item):
            return item
    return "next trading day"


def due_watch_times(now: datetime | None = None, target_date: str | None = None, include_completed: bool = False) -> list[str]:
    plan = refresh_plan(now=now, target_date=target_date)
    if include_completed:
        return plan.loc[plan["state"].isin(["due", "done"]), "time"].astype(str).tolist()
    return plan.loc[plan["state"] == "due", "time"].astype(str).tolist()


def run_refresh_slot(target_date: str, watch_time: str, source: str = "auto") -> RefreshSlot:
    try:
        result = run_watch(target_date, watch_time, source=source)
        status = "done"
        message = "refreshed" if not result.empty else "no rows; fallback template ready"
        rows = len(result)
    except Exception as exc:
        status = "failed"
        message = str(exc)
        rows = 0
    slot = RefreshSlot(target_date, watch_time, status, source, rows, message)
    save_refresh_status(target_date, [slot])
    return slot


def run_due_refreshes(
    target_date: str | None = None,
    now: datetime | None = None,
    source: str = "auto",
    include_daily: bool = False,
    include_completed: bool = False,
) -> list[RefreshSlot]:
    now = now or datetime.now()
    target_date = target_date or date.today().isoformat()
    if include_daily:
        update_all_data(end_date=target_date.replace("-", ""), use_fallback=True)
    slots = [
        run_refresh_slot(target_date, watch_time, source=source)
        for watch_time in due_watch_times(now=now, target_date=target_date, include_completed=include_completed)
    ]
    return slots


def run_scheduler_loop(poll_seconds: int | None = None, source: str = "auto") -> None:
    settings = load_settings()
    poll_seconds = poll_seconds or int(settings.get("watch.auto_refresh_interval_seconds", 60))
    while True:
        run_due_refreshes(source=source)
        time.sleep(max(poll_seconds, 15))
