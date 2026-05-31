"""Risk checks for account, trades and positions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .config import Settings, load_settings
from .constants import (
    ACCOUNT_HARD_STOP_EQUITY,
    CHASE_LIMIT_HARD,
    CHASE_LIMIT_NORMAL,
    CONSECUTIVE_LOSS_LIMIT_1,
    CONSECUTIVE_LOSS_LIMIT_2,
    HIGH_OPEN_LIMIT,
    INITIAL_CASH,
    MAIN_STOP_LOSS_RATIO,
    MAIN_TRADE_COOLDOWN_DAYS,
    MAX_ACCOUNT_LOSS_RATIO,
    TEST_STOP_LOSS_RATIO,
)
from .portfolio import Portfolio, Position
from .utils import log_risk


@dataclass
class RiskDecision:
    allowed: bool
    risk_state: str
    allow_main: bool
    only_test: bool
    reason: str = ""
    action_required: str = ""


def evaluate_account_risk(current_equity: float, settings: Settings | None = None) -> str:
    settings = settings or load_settings()
    initial_cash = float(settings.get("account.initial_cash", INITIAL_CASH))
    max_loss_ratio = float(settings.get("account.max_account_loss_ratio", MAX_ACCOUNT_LOSS_RATIO))
    if current_equity <= initial_cash * (1 - max_loss_ratio):
        return "HARD_DEFENSE"
    return "NORMAL"


def check_position_stop_loss(position: Position, current_price: float, settings: Settings | None = None) -> bool:
    settings = settings or load_settings()
    if position.avg_cost <= 0:
        return False
    ratio = current_price / position.avg_cost - 1
    if position.position_type == "TEST":
        threshold = -float(settings.get("risk.test_stop_loss_ratio", TEST_STOP_LOSS_RATIO))
    else:
        threshold = -float(settings.get("risk.main_stop_loss_ratio", MAIN_STOP_LOSS_RATIO))
    return ratio <= threshold


def chase_limit_blocks_main(
    pct_change: float,
    high_open_gap: float = 0.0,
    watch_time: str | None = None,
    settings: Settings | None = None,
) -> tuple[bool, str]:
    settings = settings or load_settings()
    hard = float(settings.get("risk.chase_limit_hard", CHASE_LIMIT_HARD))
    normal = float(settings.get("risk.chase_limit_normal", CHASE_LIMIT_NORMAL))
    high_open = float(settings.get("risk.high_open_limit", HIGH_OPEN_LIMIT))
    if pct_change > hard:
        return True, "当日涨幅超过6%，禁止新开主仓"
    if watch_time in {"10:30", "10:35"} and pct_change > normal:
        return True, "10:35涨幅超过4%，禁止主仓追入"
    if high_open_gap > high_open:
        return True, "高开超过2%，禁止开盘追入"
    return False, ""


def consecutive_loss_permission(consecutive_losses: int, settings: Settings | None = None) -> tuple[bool, bool, str]:
    settings = settings or load_settings()
    limit_1 = int(settings.get("risk.consecutive_loss_limit_1", CONSECUTIVE_LOSS_LIMIT_1))
    limit_2 = int(settings.get("risk.consecutive_loss_limit_2", CONSECUTIVE_LOSS_LIMIT_2))
    if consecutive_losses >= limit_2:
        return False, True, "连续亏损3笔，暂停主仓"
    if consecutive_losses >= limit_1:
        return True, True, "连续亏损2笔，下一笔只能测试仓"
    return True, False, ""


def evaluate_trade_permission(
    portfolio: Portfolio,
    pct_change: float = 0.0,
    high_open_gap: float = 0.0,
    watch_time: str | None = None,
    settings: Settings | None = None,
) -> RiskDecision:
    settings = settings or load_settings()
    risk_state = evaluate_account_risk(portfolio.equity, settings)
    if risk_state == "HARD_DEFENSE":
        portfolio.risk_state = risk_state
        return RiskDecision(False, risk_state, False, True, "账户触发8%硬风控", "停止主仓，只允许测试仓")
    blocked, reason = chase_limit_blocks_main(pct_change, high_open_gap, watch_time, settings)
    allow_main_by_losses, only_test, loss_reason = consecutive_loss_permission(portfolio.consecutive_losses, settings)
    allow_main = (not blocked) and allow_main_by_losses
    if blocked:
        return RiskDecision(True, risk_state, False, True, reason, "仅允许观察或测试仓")
    if only_test:
        return RiskDecision(True, risk_state, False, True, loss_reason, "下一笔限制为测试仓")
    return RiskDecision(True, risk_state, allow_main, False, "", "")


def log_account_risk_if_needed(date_value: str, portfolio: Portfolio, settings: Settings | None = None) -> str:
    state = evaluate_account_risk(portfolio.equity, settings)
    portfolio.risk_state = state
    if state == "HARD_DEFENSE":
        log_risk(date_value, "account", "HIGH", "", "当前权益触发8%账户硬风控", "停止主仓10个交易日")
    return state


def cooldown_until(trade_date: str, settings: Settings | None = None) -> str:
    settings = settings or load_settings()
    days = int(settings.get("risk.main_trade_cooldown_days", MAIN_TRADE_COOLDOWN_DAYS))
    dt = datetime.strptime(trade_date, "%Y-%m-%d").date() + timedelta(days=days)
    return dt.isoformat()
