"""Composable strategy registry for v2 signal generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from .config import Settings, load_settings
from .risk import RiskDecision
from .strategy import StrategySignal, is_pullback_buy, is_trend_chase

StrategyEvaluator = Callable[[pd.Series | dict, RiskDecision, Settings], StrategySignal | None]


@dataclass(frozen=True)
class StrategyRule:
    name: str
    label: str
    description: str
    priority: int
    evaluator: StrategyEvaluator


@dataclass(frozen=True)
class StrategyCandidate:
    rule_name: str
    label: str
    priority: int
    matched: bool
    signal: StrategySignal
    confidence: float
    explanation: str


def _float(row: pd.Series | dict, key: str, default: float = 0.0) -> float:
    value = row.get(key, default)
    if pd.isna(value):
        return default
    return float(value)


def _base_signal(row: pd.Series | dict, signal_type: str, position_type: str, amount: float, reason: str) -> StrategySignal:
    close = _float(row, "close", _float(row, "price", 0.0))
    return StrategySignal(
        date=str(row.get("date", "")),
        symbol=str(row.get("symbol", "")),
        name=str(row.get("name", "")),
        signal_type=signal_type,
        position_type=position_type,
        suggested_amount=float(amount),
        suggested_time="14:35",
        stop_loss_price=round(close * 0.94, 3) if close > 0 else 0.0,
        reason=reason,
        invalid_condition="排名、趋势、成交额或风控状态变化时失效",
    )


def _risk_limited_test(row: pd.Series | dict, risk: RiskDecision, settings: Settings) -> StrategySignal | None:
    if not risk.allowed:
        return None
    if not risk.only_test:
        return None
    if _float(row, "rank_group", 999) > 3 or not bool(row.get("trend_ok", False)):
        return None
    return _base_signal(
        row,
        "BUY_TEST",
        "TEST",
        float(settings.get("account.test_position_amount", 1000)),
        risk.reason or "风控限制下仅开放测试仓，优先验证强势标的",
    )


def _trend_chase(row: pd.Series | dict, risk: RiskDecision, settings: Settings) -> StrategySignal | None:
    if not risk.allowed or not risk.allow_main or not is_trend_chase(row, settings):
        return None
    strong = _float(row, "volume_boost", 0) >= 1.8 and _float(row, "rank_group", 999) == 1
    return _base_signal(
        row,
        "BUY_STRONG" if strong else "BUY_STANDARD",
        "STRONG" if strong else "MAIN",
        float(settings.get("account.standard_position_max" if strong else "account.standard_position_min", 3000)),
        "趋势追涨：组内排名靠前、趋势健康、放量确认且未触发追高禁入",
    )


def _pullback_buy(row: pd.Series | dict, risk: RiskDecision, settings: Settings) -> StrategySignal | None:
    if not risk.allowed or not risk.allow_main or not is_pullback_buy(row, settings):
        return None
    return _base_signal(
        row,
        "BUY_LIGHT",
        "MAIN",
        float(settings.get("account.light_position_amount", 2000)),
        "强趋势回调低吸：MA20/MA60结构未破，回撤进入可观察区",
    )


def default_strategy_registry() -> list[StrategyRule]:
    return [
        StrategyRule(
            "trend_chase",
            "趋势追涨",
            "趋势健康、组内前排、放量增强且不过热时开主仓。",
            100,
            _trend_chase,
        ),
        StrategyRule(
            "pullback_buy",
            "强趋势回调",
            "中期趋势保持，回撤靠近 MA20 且未放量破位时轻仓低吸。",
            80,
            _pullback_buy,
        ),
        StrategyRule(
            "risk_limited_test",
            "风控测试仓",
            "账户或追高规则限制主仓时，仅允许小额测试仓。",
            50,
            _risk_limited_test,
        ),
    ]


def _confidence(row: pd.Series | dict, signal: StrategySignal, priority: int) -> float:
    if signal.signal_type == "HOLD":
        return 0.0
    score = _float(row, "score", 0.0)
    rank_group = max(_float(row, "rank_group", 9), 1)
    volume_boost = max(_float(row, "volume_boost", 1.0), 0)
    trend_bonus = 0.16 if bool(row.get("trend_ok", False)) else -0.08
    score_part = max(min(score * 2.8, 0.28), -0.08)
    rank_part = max(0.16 - (rank_group - 1) * 0.05, 0.0)
    volume_part = max(min((volume_boost - 1) * 0.13, 0.16), 0.0)
    priority_part = min(priority / 1000, 0.10)
    confidence = 0.42 + score_part + rank_part + volume_part + trend_bonus + priority_part
    return float(max(0.0, min(confidence, 0.98)))


def evaluate_strategy_registry(
    row: pd.Series | dict,
    risk: RiskDecision,
    settings: Settings | None = None,
    registry: list[StrategyRule] | None = None,
) -> list[StrategyCandidate]:
    settings = settings or load_settings()
    registry = registry or default_strategy_registry()
    candidates: list[StrategyCandidate] = []
    for rule in sorted(registry, key=lambda item: item.priority, reverse=True):
        signal = rule.evaluator(row, risk, settings)
        if signal is None:
            continue
        confidence = _confidence(row, signal, rule.priority)
        candidates.append(
            StrategyCandidate(
                rule_name=rule.name,
                label=rule.label,
                priority=rule.priority,
                matched=True,
                signal=signal,
                confidence=confidence,
                explanation=f"{rule.label}命中：{signal.reason}",
            )
        )
    if candidates:
        return sorted(candidates, key=lambda item: (item.confidence, item.priority), reverse=True)
    hold = StrategySignal(
        date=str(row.get("date", "")),
        symbol=str(row.get("symbol", "")),
        name=str(row.get("name", "")),
        signal_type="HOLD",
        position_type="NONE",
        suggested_amount=0.0,
        suggested_time="14:35",
        stop_loss_price=0.0,
        reason="未命中已注册策略或被风控降级，进入观察池",
        invalid_condition="趋势、放量、排名或风控状态改善后重新评估",
    )
    return [
        StrategyCandidate(
            rule_name="watchlist",
            label="观察池",
            priority=0,
            matched=False,
            signal=hold,
            confidence=0.0,
            explanation=hold.reason,
        )
    ]


def pick_best_candidate(
    row: pd.Series | dict,
    risk: RiskDecision,
    settings: Settings | None = None,
    registry: list[StrategyRule] | None = None,
) -> StrategyCandidate:
    return evaluate_strategy_registry(row, risk, settings=settings, registry=registry)[0]
