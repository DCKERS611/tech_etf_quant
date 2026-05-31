"""Persistent risk state for daily operation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import STATE_DIR, load_settings
from .portfolio import Portfolio, Position
from .risk import evaluate_account_risk

RISK_STATE_PATH = STATE_DIR / "risk_state.json"
RISK_STATE_HISTORY_PATH = STATE_DIR / "risk_state_history.jsonl"


@dataclass
class PersistentRiskState:
    updated_at: str
    risk_state: str
    cash: float
    equity: float
    position_value: float
    realized_pnl: float
    max_equity: float
    drawdown: float
    trade_count: int
    consecutive_losses: int
    allow_main: bool
    only_test: bool
    hard_stop_equity: float
    positions: dict[str, dict[str, Any]]
    notes: list[str]


def _empty_state() -> PersistentRiskState:
    settings = load_settings()
    initial_cash = float(settings.get("account.initial_cash", 8000))
    hard_stop_equity = initial_cash * (1 - float(settings.get("account.max_account_loss_ratio", 0.08)))
    return PersistentRiskState(
        updated_at=datetime.now().isoformat(timespec="seconds"),
        risk_state="NORMAL",
        cash=initial_cash,
        equity=initial_cash,
        position_value=0.0,
        realized_pnl=0.0,
        max_equity=initial_cash,
        drawdown=0.0,
        trade_count=0,
        consecutive_losses=0,
        allow_main=True,
        only_test=False,
        hard_stop_equity=hard_stop_equity,
        positions={},
        notes=["initialized"],
    )


def portfolio_from_state(state: PersistentRiskState) -> Portfolio:
    positions = {
        symbol: Position(
            symbol=symbol,
            name=str(raw.get("name", "")),
            shares=int(raw.get("shares", 0) or 0),
            avg_cost=float(raw.get("avg_cost", 0) or 0),
            last_price=float(raw.get("last_price", 0) or 0),
            position_type=str(raw.get("position_type", "TEST")),
            open_date=str(raw.get("open_date", "")),
        )
        for symbol, raw in state.positions.items()
    }
    return Portfolio(
        cash=state.cash,
        positions=positions,
        realized_pnl=state.realized_pnl,
        max_equity=state.max_equity,
        trade_count=state.trade_count,
        consecutive_losses=state.consecutive_losses,
        risk_state=state.risk_state,
    )


def state_from_portfolio(portfolio: Portfolio, notes: list[str] | None = None) -> PersistentRiskState:
    settings = load_settings()
    risk_state = evaluate_account_risk(portfolio.equity, settings)
    initial_cash = float(settings.get("account.initial_cash", 8000))
    hard_stop_equity = initial_cash * (1 - float(settings.get("account.max_account_loss_ratio", 0.08)))
    allow_main = risk_state != "HARD_DEFENSE" and portfolio.consecutive_losses < int(
        settings.get("risk.consecutive_loss_limit_2", 3)
    )
    only_test = risk_state == "HARD_DEFENSE" or portfolio.consecutive_losses >= int(
        settings.get("risk.consecutive_loss_limit_1", 2)
    )
    snapshot = portfolio.snapshot()
    return PersistentRiskState(
        updated_at=datetime.now().isoformat(timespec="seconds"),
        risk_state=risk_state,
        cash=float(snapshot["cash"]),
        equity=float(snapshot["equity"]),
        position_value=float(snapshot["position_value"]),
        realized_pnl=float(snapshot["realized_pnl"]),
        max_equity=float(snapshot["max_equity"]),
        drawdown=float(snapshot["drawdown"]),
        trade_count=int(snapshot["trade_count"]),
        consecutive_losses=int(snapshot["consecutive_losses"]),
        allow_main=allow_main,
        only_test=only_test,
        hard_stop_equity=hard_stop_equity,
        positions=dict(snapshot["positions"]),
        notes=notes or [],
    )


def load_risk_state(path: Path | None = None) -> PersistentRiskState:
    path = path or RISK_STATE_PATH
    if not path.exists():
        return _empty_state()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return PersistentRiskState(**raw)


def save_risk_state(state: PersistentRiskState, path: Path | None = None, append_history: bool = True) -> Path:
    path = path or RISK_STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(state)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if append_history:
        RISK_STATE_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with RISK_STATE_HISTORY_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return path


def sync_risk_state(portfolio: Portfolio | None = None, notes: list[str] | None = None) -> PersistentRiskState:
    if portfolio is None:
        state = load_risk_state()
        portfolio = portfolio_from_state(state)
    state = state_from_portfolio(portfolio, notes=notes)
    save_risk_state(state)
    return state


def risk_state_dict(state: PersistentRiskState | None = None) -> dict[str, Any]:
    return asdict(state or load_risk_state())
