"""Signal generation for trend chase and strong-trend pullback entries."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .config import Settings, load_settings
from .risk import RiskDecision


@dataclass
class StrategySignal:
    date: str
    symbol: str
    name: str
    signal_type: str
    position_type: str
    suggested_amount: float
    suggested_time: str
    stop_loss_price: float
    reason: str
    invalid_condition: str = ""


def _float(row: pd.Series | dict, key: str, default: float = 0.0) -> float:
    try:
        value = row.get(key, default)
    except AttributeError:
        value = default
    if pd.isna(value):
        return default
    return float(value)


def is_trend_chase(row: pd.Series | dict, settings: Settings | None = None) -> bool:
    settings = settings or load_settings()
    min_avg_amount = float(settings.get("filters.min_avg_amount", 30_000_000))
    return (
        bool(row.get("trend_ok", False))
        and _float(row, "volume_boost", 0) >= 1.3
        and _float(row, "rank_group", 999) <= 2
        and _float(row, "amount_ma20", min_avg_amount) >= min_avg_amount
        and _float(row, "pct_change", 0) <= 0.06
    )


def is_pullback_buy(row: pd.Series | dict, settings: Settings | None = None) -> bool:
    settings = settings or load_settings()
    min_avg_amount = float(settings.get("filters.min_avg_amount", 30_000_000))
    close = _float(row, "close", 0)
    ma20 = _float(row, "ma20", 0)
    ma60 = _float(row, "ma60", 0)
    drawdown_20 = _float(row, "drawdown_from_20d_high", 0)
    volume_boost = _float(row, "volume_boost", 1)
    is_down_day = close < _float(row, "open", close)
    group_break = bool(row.get("group_break", False))
    if close <= 0 or ma20 <= 0 or ma60 <= 0:
        return False
    blocked = (
        close < ma60
        or ma20 < ma60
        or _float(row, "pct_change", 0) < -0.04
        or (volume_boost > 1.8 and is_down_day)
        or group_break
    )
    return (
        not blocked
        and close > ma60
        and ma20 > ma60
        and _float(row, "r60", 0) > 0
        and -0.08 <= drawdown_20 <= -0.03
        and close >= ma20 * 0.98
        and _float(row, "amount_ma20", min_avg_amount) >= min_avg_amount
        and _float(row, "rank_group", 999) <= 3
    )


def make_entry_signal(
    row: pd.Series | dict,
    risk: RiskDecision,
    settings: Settings | None = None,
    suggested_time: str = "14:30",
) -> StrategySignal:
    settings = settings or load_settings()
    date_value = str(row.get("date", ""))
    symbol = str(row.get("symbol", ""))
    name = str(row.get("name", ""))
    close = _float(row, "close", 0)
    if not risk.allowed:
        return StrategySignal(date_value, symbol, name, "HOLD", "NONE", 0, suggested_time, 0, risk.reason)
    if risk.only_test or not risk.allow_main:
        stop = close * (1 - float(settings.get("risk.test_stop_loss_ratio", 0.05)))
        return StrategySignal(
            date_value,
            symbol,
            name,
            "BUY_TEST",
            "TEST",
            float(settings.get("account.test_position_amount", 1000)),
            suggested_time,
            round(stop, 3),
            risk.reason or "风险限制下仅允许测试仓",
            "触发硬风控、追高限制或连续亏损限制时失效",
        )
    if is_trend_chase(row, settings):
        strong = _float(row, "volume_boost", 0) >= 1.8 and _float(row, "rank_group", 999) == 1
        signal_type = "BUY_STRONG" if strong else "BUY_STANDARD"
        position_type = "STRONG" if strong else "MAIN"
        amount = (
            float(settings.get("account.standard_position_max", 5000))
            if strong
            else float(settings.get("account.standard_position_min", 3000))
        )
        stop = close * (1 - float(settings.get("risk.main_stop_loss_ratio", 0.06)))
        return StrategySignal(
            date_value,
            symbol,
            name,
            signal_type,
            position_type,
            amount,
            suggested_time,
            round(stop, 3),
            "趋势追涨：趋势、放量、组内排名满足条件",
            "涨幅超过6%、跌破MA20或账户进入强制防守",
        )
    if is_pullback_buy(row, settings):
        stop = close * (1 - float(settings.get("risk.main_stop_loss_ratio", 0.06)))
        return StrategySignal(
            date_value,
            symbol,
            name,
            "BUY_LIGHT",
            "MAIN",
            float(settings.get("account.light_position_amount", 2000)),
            suggested_time,
            round(stop, 3),
            "强趋势回调低吸：中期趋势未破且回撤到MA20附近",
            "放量破位、跌破MA60或同组集体破位",
        )
    return StrategySignal(date_value, symbol, name, "HOLD", "NONE", 0, suggested_time, 0, "条件不足，继续观察")


def pick_primary_signal(
    ranking: pd.DataFrame,
    risk: RiskDecision,
    market_rows: dict[str, pd.Series] | None = None,
    settings: Settings | None = None,
) -> StrategySignal | None:
    if ranking.empty:
        return None
    candidates = ranking[ranking["group"] != "benchmark"].sort_values(["rank_all", "rank_group"])
    market_rows = market_rows or {}
    for row in candidates.to_dict("records"):
        enriched = dict(row)
        if row["symbol"] in market_rows:
            enriched.update(market_rows[row["symbol"]].to_dict())
            enriched.update({k: row[k] for k in row.keys()})
        signal = make_entry_signal(enriched, risk, settings=settings)
        if signal.signal_type != "HOLD":
            return signal
    top = candidates.iloc[0].to_dict() if not candidates.empty else ranking.iloc[0].to_dict()
    return make_entry_signal(top, risk, settings=settings)
