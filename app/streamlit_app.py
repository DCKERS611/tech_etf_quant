from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tech_etf_quant.backtest import run_backtest
from tech_etf_quant.config import BACKTEST_REPORT_DIR, DAILY_REPORT_DIR, LOG_DIR, STATE_DIR, load_etf_pool
from tech_etf_quant.data_loader import ensure_sample_data, latest_available_date, load_processed_data, update_all_data
from tech_etf_quant.deployment import run_deploy_health_check
from tech_etf_quant.portfolio import Portfolio
from tech_etf_quant.report import generate_daily_report
from tech_etf_quant.risk_state import load_risk_state, risk_state_dict, sync_risk_state
from tech_etf_quant.scheduler import load_refresh_status, refresh_plan, run_due_refreshes, run_refresh_slot
from tech_etf_quant.scoring import score_latest
from tech_etf_quant.signal_center import build_signal_center, latest_signal_center, summarize_signal_center
from tech_etf_quant.uzi import (
    UZI_DEPTHS,
    create_uzi_task,
    default_depth_for_command,
    ensure_uzi_repo,
    get_uzi_status,
    run_uzi_analysis,
    uzi_commands,
)
from tech_etf_quant.utils import init_project
from tech_etf_quant.watch import SNAPSHOT_COLUMNS, configured_watch_times, run_watch

st.set_page_config(page_title="A股科技ETF量化工作台", layout="wide")
init_project()

SIGNAL_TYPE_CN = {
    "BUY_TEST": "买入测试仓",
    "BUY_LIGHT": "轻仓低吸",
    "BUY_STANDARD": "标准主仓",
    "BUY_STRONG": "强势主仓",
    "HOLD": "继续观察",
    "SELL": "卖出",
    "REDUCE": "减仓",
}
POSITION_TYPE_CN = {"TEST": "测试仓", "MAIN": "主仓", "STRONG": "强势仓", "NONE": "无仓位"}
RISK_STATE_CN = {"NORMAL": "正常", "HARD_DEFENSE": "硬防守"}
REFRESH_STATE_CN = {"done": "已完成", "due": "待执行", "pending": "未到时间", "failed": "失败"}
DEPLOY_STATUS_CN = {"pass": "通过", "warn": "需检查"}
WATCH_STATUS_CN = {
    "HIGH_OPEN_BLOCK": "高开禁追",
    "WATCH": "观察",
    "OPEN_WATCH": "开盘观察",
    "CHASE_BLOCK": "追高限制",
    "PULLBACK_ALERT": "回落提醒",
    "MIDDAY_OK": "午间强势",
    "CANCEL_CHASE": "取消追涨",
    "CONFIRM": "午后确认",
    "ONLY_TEST": "只允许测试仓",
    "ACTION_ALLOWED": "允许执行",
}
SIDE_CN = {"BUY": "买入", "SELL": "卖出"}
PERFORMANCE_CN = {
    "cumulative_return": "累计收益",
    "annualized_return": "年化收益",
    "max_drawdown": "最大回撤",
    "sharpe_ratio": "夏普比率",
    "sortino_ratio": "索提诺比率",
    "annualized_volatility": "年化波动",
    "calmar_ratio": "卡玛比率",
    "trade_count": "交易次数",
    "win_rate": "胜率",
    "average_profit": "平均盈利",
    "average_loss": "平均亏损",
    "profit_loss_ratio": "盈亏比",
    "max_single_loss": "最大单笔亏损",
    "max_consecutive_losses": "最大连续亏损",
    "average_holding_days": "平均持有天数",
    "empty_days_ratio": "空仓天数占比",
    "test_only_days_ratio": "测试仓天数占比",
    "main_days_ratio": "主仓天数占比",
    "strong_days_ratio": "强势仓天数占比",
    "average_exposure": "平均仓位暴露",
    "max_exposure": "最大仓位暴露",
    "turnover": "换手倍数",
    "fee_drag": "手续费损耗",
    "slippage_drag": "滑点损耗",
    "data_days": "数据天数",
    "execution_model": "成交模型",
    "lookahead_guard": "防前视说明",
    "relative_588000": "相对科创50",
    "relative_159915": "相对创业板",
    "relative_510300": "相对沪深300",
    "signal_count": "信号数量",
}


def _metric_pct(value: float) -> str:
    return f"{float(value) * 100:.2f}%"


def _dashboard_snapshot() -> tuple[dict[str, pd.DataFrame], str, pd.DataFrame, pd.DataFrame]:
    data = load_processed_data()
    if not data:
        data = ensure_sample_data()
    latest = latest_available_date(data) or date.today().isoformat()
    ranking = score_latest(latest, save=True) if latest else pd.DataFrame()
    center = build_signal_center(latest, ranking=ranking, portfolio=Portfolio(), save=True) if not ranking.empty else pd.DataFrame()
    return data, latest, ranking, center


def _compact_signal_view(center: pd.DataFrame) -> pd.DataFrame:
    cols = ["signal_rank", "symbol", "name", "strategy", "signal_type", "confidence", "risk_permission", "explain"]
    if center.empty:
        return pd.DataFrame(columns=["序号", "代码", "名称", "策略", "信号", "置信度", "风控权限", "解释"])
    out = center[cols].copy()
    out["signal_type"] = out["signal_type"].map(lambda value: SIGNAL_TYPE_CN.get(str(value), str(value)))
    out["confidence"] = out["confidence"].map(lambda x: f"{float(x) * 100:.1f}%")
    return out.rename(
        columns={
            "signal_rank": "序号",
            "symbol": "代码",
            "name": "名称",
            "strategy": "策略",
            "signal_type": "信号",
            "confidence": "置信度",
            "risk_permission": "风控权限",
            "explain": "解释",
        }
    )


def _ranking_view(ranking: pd.DataFrame) -> pd.DataFrame:
    if ranking.empty:
        return pd.DataFrame()
    cols = ["rank_all", "rank_group", "symbol", "name", "group", "score", "trend_ok", "pct_change", "r20", "r60"]
    out = ranking[[col for col in cols if col in ranking.columns]].copy()
    if "trend_ok" in out:
        out["trend_ok"] = out["trend_ok"].map(lambda value: "是" if bool(value) else "否")
    for col in ["pct_change", "r20", "r60"]:
        if col in out:
            out[col] = out[col].map(lambda value: f"{float(value) * 100:.2f}%")
    if "score" in out:
        out["score"] = out["score"].map(lambda value: f"{float(value):.4f}")
    return out.rename(
        columns={
            "rank_all": "总排名",
            "rank_group": "组内排名",
            "symbol": "代码",
            "name": "名称",
            "group": "分组",
            "score": "分数",
            "trend_ok": "趋势健康",
            "pct_change": "涨跌幅",
            "r20": "20日强度",
            "r60": "60日强度",
        }
    )


def _refresh_plan_view(plan: pd.DataFrame) -> pd.DataFrame:
    if plan.empty:
        return pd.DataFrame(columns=["日期", "时间", "状态"])
    out = plan.copy()
    out["state"] = out["state"].map(lambda value: REFRESH_STATE_CN.get(str(value), str(value)))
    return out.rename(columns={"date": "日期", "time": "时间", "state": "状态"})


def _refresh_status_view(status: pd.DataFrame) -> pd.DataFrame:
    if status.empty:
        return pd.DataFrame(columns=["日期", "时间", "状态", "数据来源", "行数", "说明"])
    out = status.copy()
    out["status"] = out["status"].map(lambda value: REFRESH_STATE_CN.get(str(value), str(value)))
    return out.rename(columns={"date": "日期", "time": "时间", "status": "状态", "source": "数据来源", "rows": "行数", "message": "说明"})


def _risk_dict_cn(raw: dict) -> dict:
    return {
        "更新时间": raw.get("updated_at", ""),
        "风控状态": RISK_STATE_CN.get(str(raw.get("risk_state", "")), str(raw.get("risk_state", ""))),
        "现金": raw.get("cash", 0),
        "权益": raw.get("equity", 0),
        "持仓市值": raw.get("position_value", 0),
        "已实现盈亏": raw.get("realized_pnl", 0),
        "最大权益": raw.get("max_equity", 0),
        "当前回撤": raw.get("drawdown", 0),
        "交易次数": raw.get("trade_count", 0),
        "连续亏损": raw.get("consecutive_losses", 0),
        "是否允许主仓": "是" if raw.get("allow_main") else "否",
        "是否只允许测试仓": "是" if raw.get("only_test") else "否",
        "硬止损线": raw.get("hard_stop_equity", 0),
        "持仓": raw.get("positions", {}),
        "备注": raw.get("notes", []),
    }


def _performance_view(raw: dict) -> pd.DataFrame:
    return pd.DataFrame(
        [[PERFORMANCE_CN.get(str(key), str(key)), value] for key, value in raw.items()],
        columns=["指标", "数值"],
    )


def _trade_view(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "side" in out:
        out["side"] = out["side"].map(lambda value: SIDE_CN.get(str(value), str(value)))
    if "signal_type" in out:
        out["signal_type"] = out["signal_type"].map(lambda value: SIGNAL_TYPE_CN.get(str(value), str(value)))
    if "position_type" in out:
        out["position_type"] = out["position_type"].map(lambda value: POSITION_TYPE_CN.get(str(value), str(value)))
    return out.rename(
        columns={
            "date": "日期",
            "time": "时间",
            "symbol": "代码",
            "name": "名称",
            "side": "方向",
            "shares": "份额",
            "price": "价格",
            "amount": "金额",
            "commission": "手续费",
            "slippage": "滑点",
            "position_type": "仓位类型",
            "reason": "原因",
            "signal_type": "信号",
            "cash_after": "成交后现金",
            "equity_after": "成交后权益",
            "realized_pnl": "已实现盈亏",
            "realized_pnl_ratio": "已实现盈亏率",
        }
    )


def _watch_log_view(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "status" in out:
        out["status"] = out["status"].map(lambda value: WATCH_STATUS_CN.get(str(value), str(value)))
    return out.rename(
        columns={
            "date": "日期",
            "time": "时间",
            "symbol": "代码",
            "price": "价格",
            "pct_change": "涨跌幅",
            "amount": "成交额",
            "status": "状态",
            "watch_decision": "观察结论",
            "note": "备注",
        }
    )


def _backtest_signal_view(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "signal_type" in out:
        out["signal_type"] = out["signal_type"].map(lambda value: SIGNAL_TYPE_CN.get(str(value), str(value)))
    if "position_type" in out:
        out["position_type"] = out["position_type"].map(lambda value: POSITION_TYPE_CN.get(str(value), str(value)))
    return out.rename(
        columns={
            "date": "日期",
            "symbol": "代码",
            "name": "名称",
            "signal_type": "信号",
            "position_type": "仓位类型",
            "suggested_amount": "建议金额",
            "suggested_time": "建议时间",
            "stop_loss_price": "止损价",
            "reason": "原因",
            "invalid_condition": "失效条件",
            "next_execution_date": "次日执行日期",
        }
    )


def _auto_refresh(seconds: int) -> None:
    components.html(
        f"""
        <script>
        setTimeout(function() {{
            window.parent.location.reload();
        }}, {max(int(seconds), 10) * 1000});
        </script>
        """,
        height=0,
    )


def _daily_auto_update_once() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    marker = STATE_DIR / "streamlit_auto_daily_update.txt"
    today = date.today().isoformat()
    if marker.exists() and marker.read_text(encoding="utf-8").strip() == today:
        return
    with st.spinner("正在自动更新日线数据"):
        update_all_data(end_date=today.replace("-", ""), use_fallback=True)
    marker.write_text(today, encoding="utf-8")
    st.success("今日日线数据已自动更新")


st.title("A股科技ETF量化工作台 v2.0")
st.caption("个人学习用途，不作为投资参考。")

with st.sidebar:
    st.subheader("运行状态")
    state = load_risk_state()
    plan_now = refresh_plan()
    pending_now = plan_now.query("state == 'pending'") if not plan_now.empty else pd.DataFrame()
    next_slot = str(pending_now["time"].iloc[0]) if not pending_now.empty else "-"
    st.metric("风控状态", RISK_STATE_CN.get(state.risk_state, state.risk_state))
    st.metric("权益", f"{state.equity:.2f}")
    st.metric("下次刷新", next_slot)
    st.divider()
    page_auto_refresh = st.toggle("自动刷新网页", value=True)
    refresh_seconds = st.number_input("刷新间隔（秒）", min_value=30, max_value=600, value=60, step=30)
    auto_daily_update = st.toggle("每日自动更新日线", value=True)
    auto_run_due = st.toggle("自动执行到期刷新", value=True)
    if auto_daily_update:
        _daily_auto_update_once()
    if page_auto_refresh:
        _auto_refresh(int(refresh_seconds))
    if auto_run_due:
        slots = run_due_refreshes(date.today().isoformat(), include_daily=False)
        if slots:
            st.success(f"已自动执行 {len(slots)} 个到期刷新")
    if st.button("同步风控状态", use_container_width=True):
        state = sync_risk_state(notes=["streamlit sidebar sync"])
        st.success(RISK_STATE_CN.get(state.risk_state, state.risk_state))

tabs = st.tabs(
    [
        "工作台",
        "信号中心",
        "盘中刷新",
        "风控状态",
        "回测实验室",
        "报告中心",
        "配置数据",
        "部署健康",
        "UZI项目分析",
    ]
)

with tabs[0]:
    data, latest, ranking, center = _dashboard_snapshot()
    summary = summarize_signal_center(center)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("最新交易日", latest)
    c2.metric("ETF数量", len(data))
    c3.metric("可行动信号", summary["actionable"])
    c4.metric("平均置信度", _metric_pct(summary["avg_confidence"]))
    c5.metric("刷新槽", len(configured_watch_times()))
    if summary["top"]:
        top = summary["top"]
        st.info(f"{top['symbol']} {top['name']} / {SIGNAL_TYPE_CN.get(str(top['signal_type']), str(top['signal_type']))} / {float(top['confidence']) * 100:.1f}%")
    st.dataframe(_compact_signal_view(center).head(8), use_container_width=True, hide_index=True)
    st.divider()
    left, right = st.columns([1, 1])
    with left:
        st.subheader("今日排名")
        st.dataframe(_ranking_view(ranking).head(10), use_container_width=True, hide_index=True)
    with right:
        st.subheader("刷新计划")
        st.dataframe(_refresh_plan_view(refresh_plan(target_date=date.today().isoformat())), use_container_width=True, hide_index=True)

with tabs[1]:
    signal_date = st.date_input("信号日期", value=date.today(), key="signal_date").isoformat()
    c1, c2 = st.columns([1, 1])
    if c1.button("重建信号中心", type="primary"):
        center = build_signal_center(signal_date, save=True)
    else:
        center = latest_signal_center(signal_date)
        if center.empty:
            center = build_signal_center(signal_date, save=True)
    if c2.button("更新日线并重建"):
        update_all_data(end_date=signal_date.replace("-", ""), use_fallback=True)
        center = build_signal_center(signal_date, save=True)
    st.dataframe(_compact_signal_view(center), use_container_width=True, hide_index=True)
    if not center.empty:
        selected = st.selectbox(
            "信号解释",
            center["symbol"].tolist(),
            format_func=lambda symbol: f"{symbol} {center[center['symbol'] == symbol].iloc[0]['name']}",
        )
        row = center[center["symbol"] == selected].iloc[0]
        st.table(
            pd.DataFrame(
                [
                    ["信号", SIGNAL_TYPE_CN.get(str(row["signal_type"]), str(row["signal_type"]))],
                    ["策略", row["strategy"]],
                    ["置信度", f"{float(row['confidence']) * 100:.1f}%"],
                    ["风控权限", row["risk_permission"]],
                    ["解释", row["explain"]],
                    ["失效条件", row["invalid_condition"]],
                ],
                columns=["项目", "内容"],
            )
        )

with tabs[2]:
    watch_times = configured_watch_times()
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    auto_date = c1.date_input("刷新日期", value=date.today(), key="watch_date").isoformat()
    auto_time = c2.selectbox("刷新时间", watch_times, index=min(1, len(watch_times) - 1))
    if c3.button("运行当前槽", type="primary"):
        slot = run_refresh_slot(auto_date, auto_time)
        st.success(slot.message)
    if c4.button("运行到期槽"):
        slots = run_due_refreshes(auto_date, include_daily=False)
        st.success(f"已运行 {len(slots)} 个到期刷新")
    st.dataframe(_refresh_plan_view(refresh_plan(target_date=auto_date)), use_container_width=True, hide_index=True)
    status = load_refresh_status(auto_date)
    if not status.empty:
        st.dataframe(_refresh_status_view(status), use_container_width=True, hide_index=True)
    with st.expander("手动CSV兜底"):
        with st.form("snapshot_form"):
            c1, c2, c3, c4 = st.columns(4)
            snap_date = c1.date_input("快照日期", value=date.today(), key="snap_date").isoformat()
            snap_time = c2.selectbox("时间", watch_times, key="snap_time")
            symbol = c3.text_input("代码", value="512480")
            price = c4.number_input("价格", min_value=0.0, value=1.000, step=0.001, format="%.3f")
            c5, c6, c7, c8 = st.columns(4)
            pct_change = c5.number_input("涨幅", value=0.0, step=0.001, format="%.3f")
            amount = c6.number_input("成交额", min_value=0.0, value=30000000.0, step=1000000.0)
            high = c7.number_input("最高", min_value=0.0, value=1.020, step=0.001, format="%.3f")
            low = c8.number_input("最低", min_value=0.0, value=0.990, step=0.001, format="%.3f")
            c9, c10, c11 = st.columns(3)
            open_price = c9.number_input("开盘", min_value=0.0, value=1.000, step=0.001, format="%.3f")
            prev_close = c10.number_input("昨收", min_value=0.0, value=1.000, step=0.001, format="%.3f")
            volume = c11.number_input("成交量", min_value=0.0, value=10000000.0, step=1000000.0)
            note = st.text_input("备注", value="")
            submitted = st.form_submit_button("记录兜底快照")
        if submitted:
            tmp = ROOT / "data" / "snapshots" / "_streamlit_snapshot.csv"
            row = pd.DataFrame(
                [
                    {
                        "date": snap_date,
                        "time": snap_time,
                        "symbol": symbol,
                        "price": price,
                        "pct_change": pct_change,
                        "amount": amount,
                        "volume": volume,
                        "high": high,
                        "low": low,
                        "open": open_price,
                        "prev_close": prev_close,
                        "note": note,
                    }
                ],
                columns=SNAPSHOT_COLUMNS,
            )
            row.to_csv(tmp, index=False, encoding="utf-8")
            result = run_watch(snap_date, snap_time, tmp, source="manual")
            st.dataframe(result, use_container_width=True, hide_index=True)

with tabs[3]:
    state = load_risk_state()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("状态", RISK_STATE_CN.get(state.risk_state, state.risk_state))
    c2.metric("权益", f"{state.equity:.2f}")
    c3.metric("硬止损线", f"{state.hard_stop_equity:.2f}")
    c4.metric("连续亏损", state.consecutive_losses)
    if st.button("写入当前风控快照", type="primary"):
        state = sync_risk_state(notes=["streamlit risk tab sync"])
        st.success(RISK_STATE_CN.get(state.risk_state, state.risk_state))
    st.table(pd.DataFrame(_risk_dict_cn(risk_state_dict(state)).items(), columns=["项目", "内容"]))
    risk_log = LOG_DIR / "risk_log.csv"
    if risk_log.exists():
        st.dataframe(pd.read_csv(risk_log), use_container_width=True, hide_index=True)

with tabs[4]:
    c1, c2, c3 = st.columns([1, 1, 1])
    start = c1.date_input("开始日期", value=pd.Timestamp("2024-01-01"), key="bt_start").isoformat()
    end = c2.date_input("结束日期", value=date.today(), key="bt_end").isoformat()
    if c3.button("运行回测", type="primary"):
        result = run_backtest(start, end)
        st.table(_performance_view(result["performance"]))
    perf_path = BACKTEST_REPORT_DIR / "performance.json"
    equity_path = BACKTEST_REPORT_DIR / "equity_curve.csv"
    trades_path = BACKTEST_REPORT_DIR / "trades.csv"
    signals_path = BACKTEST_REPORT_DIR / "signals.csv"
    if perf_path.exists():
        import json

        st.table(_performance_view(json.loads(perf_path.read_text(encoding="utf-8"))))
    if equity_path.exists():
        equity = pd.read_csv(equity_path)
        st.line_chart(equity.set_index("date")["equity"])
    cols = st.columns([1, 1])
    with cols[0]:
        if trades_path.exists():
            st.dataframe(_trade_view(pd.read_csv(trades_path, dtype={"symbol": str})), use_container_width=True, hide_index=True)
    with cols[1]:
        if signals_path.exists():
            st.dataframe(_backtest_signal_view(pd.read_csv(signals_path, dtype={"symbol": str})), use_container_width=True, hide_index=True)

with tabs[5]:
    report_date = st.date_input("报告日期", value=date.today(), key="report_date").isoformat()
    if st.button("生成专业日报", type="primary"):
        paths = generate_daily_report(report_date)
        st.success(paths["markdown"].name)
    md_path = DAILY_REPORT_DIR / f"{report_date}_daily_report.md"
    if md_path.exists():
        st.markdown(md_path.read_text(encoding="utf-8"))

with tabs[6]:
    pool = load_etf_pool(enabled_only=False)
    st.subheader("ETF池")
    st.dataframe(
        pool.rename(
            columns={
                "symbol": "代码",
                "name": "名称",
                "group": "分组",
                "role": "角色",
                "priority": "优先级",
                "enabled": "启用",
                "notes": "备注",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
    trade_log = LOG_DIR / "trade_log.csv"
    watch_log = LOG_DIR / "watch_log.csv"
    cols = st.columns([1, 1])
    with cols[0]:
        st.subheader("交易日志")
        if trade_log.exists():
            st.dataframe(_trade_view(pd.read_csv(trade_log, dtype={"symbol": str})), use_container_width=True, hide_index=True)
    with cols[1]:
        st.subheader("观察日志")
        if watch_log.exists():
            st.dataframe(_watch_log_view(pd.read_csv(watch_log, dtype={"symbol": str})), use_container_width=True, hide_index=True)

with tabs[7]:
    if st.button("运行部署检查", type="primary"):
        health = run_deploy_health_check()
    else:
        health = run_deploy_health_check()
    c1, c2 = st.columns([1, 1])
    c1.metric("状态", DEPLOY_STATUS_CN.get(str(health["status"]), str(health["status"])))
    c2.metric("网页主文件路径", health["main_file_path"])
    checks = pd.DataFrame(health["checks"])
    if not checks.empty:
        checks["ok"] = checks["ok"].map(lambda value: "通过" if bool(value) else "需检查")
        checks = checks.rename(columns={"name": "检查项", "ok": "结果", "message": "说明"})
    st.dataframe(checks, use_container_width=True, hide_index=True)

with tabs[8]:
    status = get_uzi_status()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("作用域", "当前项目")
    c2.metric("本地引擎", "就绪" if status.installed else "未准备")
    c3.metric("版本", status.current_commit or "-")
    c4.metric("输出目录", "reports/uzi")

    p1, p2 = st.columns([1, 1])
    if p1.button("准备 UZI 引擎", type="primary"):
        status = ensure_uzi_repo(update=False)
        st.success(status.message)
    if p2.button("更新 UZI 引擎"):
        status = ensure_uzi_repo(update=True)
        st.success(status.message)

    commands = uzi_commands()
    keys = list(commands.keys())
    form_cols = st.columns([1.2, 1, 0.8, 0.8])
    target = form_cols[0].text_input("标的", value="512480", key="uzi_target")
    analysis_command = form_cols[1].selectbox(
        "类型",
        keys,
        index=keys.index("quick-scan") if "quick-scan" in keys else 0,
        format_func=lambda key: commands[key].get("label", key),
        key="uzi_command",
    )
    default_depth = default_depth_for_command(analysis_command)
    depth = form_cols[2].selectbox("深度", UZI_DEPTHS, index=UZI_DEPTHS.index(default_depth), key="uzi_depth")
    timeout_seconds = int(form_cols[3].number_input("超时秒", min_value=120, max_value=7200, value=1800, step=120))

    a1, a2 = st.columns([1, 1])
    if a1.button("生成任务"):
        task = create_uzi_task(target=target, command=analysis_command, depth=depth)
        st.success(task["markdown_path"])
        st.json(
            {"分析指令": task["slash_command"], "运行命令": " ".join(task["run_command"]), "输出目录": task["output_dir"]}
        )
    if a2.button("运行分析"):
        with st.spinner("UZI 分析运行中"):
            result = run_uzi_analysis(
                target=target,
                command=analysis_command,
                depth=depth,
                timeout_seconds=timeout_seconds,
            )
        if result.ok:
            st.success(result.output_dir)
        else:
            st.error(result.message)
        if result.stdout:
            st.code(result.stdout[-8000:], language="text")
        if result.stderr:
            st.code(result.stderr[-8000:], language="text")
