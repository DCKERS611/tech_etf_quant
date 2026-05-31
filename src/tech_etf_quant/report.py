"""Daily report generation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .charts import generate_daily_charts
from .config import DAILY_REPORT_DIR, Settings, load_settings
from .constants import ETF_GROUP_NAMES
from .data_loader import ensure_sample_data, load_processed_data
from .portfolio import Portfolio
from .risk import evaluate_trade_permission
from .scoring import calculate_scores, save_ranking
from .signal_center import build_signal_center
from .strategy import pick_primary_signal


def _format_pct(value: float) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except Exception:
        return ""


def _ranking_table(ranking: pd.DataFrame, group: str) -> str:
    part = ranking[ranking["group"] == group].copy()
    if part.empty:
        return "暂无数据"
    part["趋势"] = part["trend_ok"].map(lambda x: "是" if bool(x) else "否")
    part = part.rename(
        columns={
            "rank_group": "排名",
            "symbol": "代码",
            "name": "名称",
            "score": "分数",
            "pct_change": "涨幅",
            "r20": "R20",
            "r60": "R60",
            "volume_boost": "放量",
        }
    )
    display = part[["排名", "代码", "名称", "分数", "趋势", "涨幅", "R20", "R60", "放量"]].copy()
    for col in ["分数", "放量"]:
        display[col] = display[col].map(lambda x: f"{x:.3f}")
    for col in ["涨幅", "R20", "R60"]:
        display[col] = display[col].map(_format_pct)
    return display.to_markdown(index=False)


def _market_table(ranking: pd.DataFrame) -> str:
    part = ranking[ranking["group"] == "benchmark"].copy()
    if part.empty:
        return "暂无基准数据"
    part["状态"] = part["trend_ok"].map(lambda x: "趋势健康" if bool(x) else "偏弱/震荡")
    display = part[["name", "close", "ma20", "ma60", "r20", "r60", "状态"]].rename(
        columns={"name": "指数/ETF", "close": "收盘价", "ma20": "MA20", "ma60": "MA60", "r20": "R20", "r60": "R60"}
    )
    for col in ["收盘价", "MA20", "MA60"]:
        display[col] = display[col].map(lambda x: f"{x:.3f}")
    for col in ["R20", "R60"]:
        display[col] = display[col].map(_format_pct)
    return display.to_markdown(index=False)


def _signal_center_table(signal_center: pd.DataFrame) -> str:
    if signal_center.empty:
        return "暂无信号中心数据"
    display = signal_center.head(8)[
        [
            "signal_rank",
            "symbol",
            "name",
            "strategy",
            "signal_type",
            "confidence",
            "risk_permission",
            "explain",
        ]
    ].rename(
        columns={
            "signal_rank": "序",
            "symbol": "代码",
            "name": "名称",
            "strategy": "策略",
            "signal_type": "信号",
            "confidence": "置信度",
            "risk_permission": "权限",
            "explain": "解释",
        }
    )
    display["置信度"] = display["置信度"].map(lambda x: f"{float(x) * 100:.1f}%")
    return display.to_markdown(index=False)


def build_daily_report_markdown(
    target_date: str,
    ranking: pd.DataFrame,
    portfolio: Portfolio,
    signal,
    risk_decision,
    signal_center: pd.DataFrame | None = None,
) -> str:
    current_return = portfolio.equity / 8000 - 1
    hard_stop_left = portfolio.equity - 7360
    positions_text = ", ".join(
        f"{pos.symbol} {pos.name} {pos.shares}份 {pos.position_type}" for pos in portfolio.positions.values()
    ) or "无持仓"
    primary = signal.symbol + " " + signal.name if signal else "暂无"
    backup_rows = ranking[(ranking["group"] != "benchmark") & (ranking["symbol"] != (signal.symbol if signal else ""))].head(2)
    backup = ", ".join(backup_rows["symbol"] + " " + backup_rows["name"]) if not backup_rows.empty else "暂无"
    sections = [
        f"# 每日交易报告 - {target_date}",
        "## 1. 账户状态",
        f"- 初始本金：8000.00",
        f"- 当前权益：{portfolio.equity:.2f}",
        f"- 当前现金：{portfolio.cash:.2f}",
        f"- 当前持仓：{positions_text}",
        f"- 当前收益：{_format_pct(current_return)}",
        f"- 当前回撤：{_format_pct(portfolio.drawdown)}",
        f"- 距离8%硬止损线还剩：{hard_stop_left:.2f}",
        "## 2. 市场状态",
        _market_table(ranking),
        "## 3. ETF分组排名",
    ]
    for group in ["semiconductor", "cpo_pcb", "electronics_mlcc", "rare_earth"]:
        sections.extend([f"### {ETF_GROUP_NAMES[group]}", _ranking_table(ranking, group)])
    sections.extend(
        [
            "## 4. 今日信号",
            f"- 首选ETF：{primary}",
            f"- 备选ETF：{backup}",
            f"- 信号类型：{signal.signal_type if signal else 'HOLD'}",
            f"- 建议动作：{signal.reason if signal else '继续观察'}",
            f"- 建议金额：{signal.suggested_amount if signal else 0:.2f}",
            f"- 建议时间：{signal.suggested_time if signal else '14:30'}",
            f"- 止损价：{signal.stop_loss_price if signal else 0:.3f}",
            f"- 失效条件：{signal.invalid_condition if signal else '排名、趋势或风控条件变化'}",
            "## 5. 可解释信号中心",
            _signal_center_table(signal_center if signal_center is not None else pd.DataFrame()),
            "## 6. 风控检查",
            f"- 是否触发账户硬风控：{'是' if portfolio.risk_state == 'HARD_DEFENSE' else '否'}",
            "- 是否触发单笔止损：需结合当前持仓成本盘中确认",
            f"- 是否触发追高限制：{'是' if risk_decision.only_test and '涨幅' in risk_decision.reason else '否'}",
            f"- 是否触发连续亏损限制：{'是' if '连续亏损' in risk_decision.reason else '否'}",
            f"- 是否允许主仓：{'是' if risk_decision.allow_main else '否'}",
            f"- 是否只允许测试仓：{'是' if risk_decision.only_test else '否'}",
            "## 7. 明日计划",
            "- 9:35：集合竞价后自动拉取实时行情，确认高开和开盘质量",
            "- 10:35：自动刷新涨幅、放量和高开状态，主仓不追高",
            "- 午休：检查冲高回落与同组强弱",
            "- 13:30：自动刷新午后延续性，快速回落则取消追涨计划",
            "- 14:35：按排名、趋势、风控状态决定测试仓/主仓/减仓",
        ]
    )
    return "\n\n".join(sections) + "\n"


def markdown_to_basic_html(markdown_text: str, ranking: pd.DataFrame) -> str:
    return f"""
<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>Daily Report</title></head>
<body>
<pre style="white-space: pre-wrap; font-family: Consolas, monospace;">{markdown_text}</pre>
<h2>排名明细</h2>
{ranking.to_html(index=False)}
</body>
</html>
"""


def generate_daily_report(
    target_date: str,
    ranking: pd.DataFrame | None = None,
    portfolio: Portfolio | None = None,
    settings: Settings | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    settings = settings or load_settings()
    output_dir = output_dir or DAILY_REPORT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    data = load_processed_data()
    if not data:
        data = ensure_sample_data(end_date=target_date)
    if ranking is None:
        ranking = calculate_scores(data, target_date=target_date, settings=settings)
        save_ranking(ranking, target_date, output_dir)
    portfolio = portfolio or Portfolio(cash=float(settings.get("account.initial_cash", 8000)))
    top = ranking[ranking["group"] != "benchmark"].head(1)
    pct_change = float(top.iloc[0]["pct_change"]) if not top.empty else 0.0
    risk_decision = evaluate_trade_permission(portfolio, pct_change=pct_change, watch_time="14:30", settings=settings)
    signal = pick_primary_signal(ranking, risk_decision, settings=settings)
    signal_center = build_signal_center(target_date, ranking=ranking, portfolio=portfolio, settings=settings, save=False)
    markdown_text = build_daily_report_markdown(target_date, ranking, portfolio, signal, risk_decision, signal_center)
    md_path = output_dir / f"{target_date}_daily_report.md"
    html_path = output_dir / f"{target_date}_daily_report.html"
    md_path.write_text(markdown_text, encoding="utf-8")
    html_path.write_text(markdown_to_basic_html(markdown_text, ranking), encoding="utf-8")
    generate_daily_charts(ranking)
    return {"markdown": md_path, "html": html_path}
