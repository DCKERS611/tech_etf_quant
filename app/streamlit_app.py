from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tech_etf_quant.backtest import run_backtest
from tech_etf_quant.config import BACKTEST_REPORT_DIR, DAILY_REPORT_DIR, LOG_DIR, load_etf_pool
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

st.set_page_config(page_title="Tech ETF Quant v2", layout="wide")
init_project()


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
    cols = [
        "signal_rank",
        "symbol",
        "name",
        "strategy",
        "signal_type",
        "confidence",
        "risk_permission",
        "explain",
    ]
    if center.empty:
        return pd.DataFrame(columns=cols)
    out = center[cols].copy()
    out["confidence"] = out["confidence"].map(lambda x: f"{float(x) * 100:.1f}%")
    return out


st.title("A股科技ETF量化工作台 v2.0")
st.caption("个人学习用途，不作为投资参考。")

with st.sidebar:
    st.subheader("运行状态")
    state = load_risk_state()
    plan_now = refresh_plan()
    pending_now = plan_now.query("state == 'pending'") if not plan_now.empty else pd.DataFrame()
    next_slot = str(pending_now["time"].iloc[0]) if not pending_now.empty else "-"
    st.metric("风控状态", state.risk_state)
    st.metric("权益", f"{state.equity:.2f}")
    st.metric("下次刷新", next_slot)
    if st.button("同步风控状态", use_container_width=True):
        state = sync_risk_state(notes=["streamlit sidebar sync"])
        st.success(state.risk_state)

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
        st.info(f"{top['symbol']} {top['name']} / {top['signal_type']} / {float(top['confidence']) * 100:.1f}%")
    st.dataframe(_compact_signal_view(center).head(8), use_container_width=True, hide_index=True)
    st.divider()
    left, right = st.columns([1, 1])
    with left:
        st.subheader("今日排名")
        st.dataframe(ranking.head(10), use_container_width=True, hide_index=True)
    with right:
        st.subheader("刷新计划")
        st.dataframe(refresh_plan(target_date=date.today().isoformat()), use_container_width=True, hide_index=True)

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
        st.json(
            {
                "signal": row["signal_type"],
                "strategy": row["strategy"],
                "confidence": row["confidence"],
                "risk": row["risk_permission"],
                "explain": row["explain"],
                "invalid_condition": row["invalid_condition"],
            }
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
        st.json([slot.__dict__ for slot in slots])
    st.dataframe(refresh_plan(target_date=auto_date), use_container_width=True, hide_index=True)
    status = load_refresh_status(auto_date)
    if not status.empty:
        st.dataframe(status, use_container_width=True, hide_index=True)
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
    c1.metric("状态", state.risk_state)
    c2.metric("权益", f"{state.equity:.2f}")
    c3.metric("硬止损线", f"{state.hard_stop_equity:.2f}")
    c4.metric("连续亏损", state.consecutive_losses)
    if st.button("写入当前风控快照", type="primary"):
        state = sync_risk_state(notes=["streamlit risk tab sync"])
        st.success(state.risk_state)
    st.json(risk_state_dict(state))
    risk_log = LOG_DIR / "risk_log.csv"
    if risk_log.exists():
        st.dataframe(pd.read_csv(risk_log), use_container_width=True, hide_index=True)

with tabs[4]:
    c1, c2, c3 = st.columns([1, 1, 1])
    start = c1.date_input("开始日期", value=pd.Timestamp("2024-01-01"), key="bt_start").isoformat()
    end = c2.date_input("结束日期", value=date.today(), key="bt_end").isoformat()
    if c3.button("运行回测", type="primary"):
        result = run_backtest(start, end)
        st.json(result["performance"])
    perf_path = BACKTEST_REPORT_DIR / "performance.json"
    equity_path = BACKTEST_REPORT_DIR / "equity_curve.csv"
    trades_path = BACKTEST_REPORT_DIR / "trades.csv"
    signals_path = BACKTEST_REPORT_DIR / "signals.csv"
    if perf_path.exists():
        st.json(perf_path.read_text(encoding="utf-8"))
    if equity_path.exists():
        equity = pd.read_csv(equity_path)
        st.line_chart(equity.set_index("date")["equity"])
    cols = st.columns([1, 1])
    with cols[0]:
        if trades_path.exists():
            st.dataframe(pd.read_csv(trades_path, dtype={"symbol": str}), use_container_width=True, hide_index=True)
    with cols[1]:
        if signals_path.exists():
            st.dataframe(pd.read_csv(signals_path, dtype={"symbol": str}), use_container_width=True, hide_index=True)

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
    st.dataframe(pool, use_container_width=True, hide_index=True)
    trade_log = LOG_DIR / "trade_log.csv"
    watch_log = LOG_DIR / "watch_log.csv"
    cols = st.columns([1, 1])
    with cols[0]:
        st.subheader("交易日志")
        if trade_log.exists():
            st.dataframe(pd.read_csv(trade_log, dtype={"symbol": str}), use_container_width=True, hide_index=True)
    with cols[1]:
        st.subheader("观察日志")
        if watch_log.exists():
            st.dataframe(pd.read_csv(watch_log, dtype={"symbol": str}), use_container_width=True, hide_index=True)

with tabs[7]:
    if st.button("运行部署检查", type="primary"):
        health = run_deploy_health_check()
    else:
        health = run_deploy_health_check()
    c1, c2 = st.columns([1, 1])
    c1.metric("状态", health["status"])
    c2.metric("Main file path", health["main_file_path"])
    st.dataframe(pd.DataFrame(health["checks"]), use_container_width=True, hide_index=True)

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
        format_func=lambda key: f"{key} / {commands[key].get('label', key)}",
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
            {
                "slash_command": task["slash_command"],
                "run_command": " ".join(task["run_command"]),
                "output_dir": task["output_dir"],
            }
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
