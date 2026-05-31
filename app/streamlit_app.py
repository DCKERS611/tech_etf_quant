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
from tech_etf_quant.data_loader import ensure_sample_data, latest_available_date, load_processed_data
from tech_etf_quant.portfolio import Portfolio
from tech_etf_quant.report import generate_daily_report
from tech_etf_quant.scoring import score_latest
from tech_etf_quant.utils import init_project
from tech_etf_quant.watch import SNAPSHOT_COLUMNS, configured_watch_times, run_watch

st.set_page_config(page_title="Tech ETF Quant", layout="wide")
init_project()

st.title("A股科技ETF量化辅助系统")

tabs = st.tabs(["首页概览", "ETF池", "今日排名", "风控状态", "每日交易报告", "回测结果", "交易日志", "盘中自动刷新"])

with tabs[0]:
    data = load_processed_data()
    if not data:
        data = ensure_sample_data()
    latest = latest_available_date(data) or ""
    ranking = score_latest(latest, save=True) if latest else pd.DataFrame()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("最新交易日", latest)
    c2.metric("ETF数量", len(data))
    c3.metric("首位ETF", "" if ranking.empty else f"{ranking.iloc[0]['symbol']} {ranking.iloc[0]['name']}")
    c4.metric("首位分数", "" if ranking.empty else f"{ranking.iloc[0]['score']:.4f}")
    c5.metric("盘中源", "自动优先")
    if not ranking.empty:
        st.dataframe(ranking.head(10), use_container_width=True, hide_index=True)

with tabs[1]:
    pool = load_etf_pool(enabled_only=False)
    st.dataframe(pool, use_container_width=True, hide_index=True)

with tabs[2]:
    target_date = st.date_input("日期").isoformat()
    if st.button("刷新排名", type="primary"):
        ranking = score_latest(target_date, save=True)
    else:
        ranking_path = DAILY_REPORT_DIR / f"{target_date}_ranking.csv"
        ranking = pd.read_csv(ranking_path, dtype={"symbol": str}) if ranking_path.exists() else pd.DataFrame()
    st.dataframe(ranking, use_container_width=True, hide_index=True)

with tabs[3]:
    portfolio = Portfolio()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("当前权益", f"{portfolio.equity:.2f}")
    c2.metric("现金", f"{portfolio.cash:.2f}")
    c3.metric("硬风控线", "7360.00")
    c4.metric("状态", portfolio.risk_state)
    st.table(
        pd.DataFrame(
            [
                ["账户8%硬风控", "未触发" if portfolio.equity > 7360 else "触发"],
                ["测试仓止损", "5%"],
                ["主仓止损", "6%"],
                ["现金保留", "1000元"],
                ["最大持仓", "6400元"],
            ],
            columns=["项目", "状态"],
        )
    )

with tabs[4]:
    report_date = st.date_input("报告日期").isoformat()
    if st.button("生成日报", type="primary"):
        paths = generate_daily_report(report_date)
        st.success(f"已生成 {paths['markdown'].name}")
    md_path = DAILY_REPORT_DIR / f"{report_date}_daily_report.md"
    if md_path.exists():
        st.markdown(md_path.read_text(encoding="utf-8"))

with tabs[5]:
    c1, c2, c3 = st.columns([1, 1, 1])
    start = c1.date_input("开始日期", value=pd.Timestamp("2024-01-01")).isoformat()
    end = c2.date_input("结束日期").isoformat()
    if c3.button("运行回测", type="primary"):
        result = run_backtest(start, end)
        st.json(result["performance"])
    perf_path = BACKTEST_REPORT_DIR / "performance.json"
    equity_path = BACKTEST_REPORT_DIR / "equity_curve.csv"
    trades_path = BACKTEST_REPORT_DIR / "trades.csv"
    if perf_path.exists():
        st.json(perf_path.read_text(encoding="utf-8"))
    if equity_path.exists():
        equity = pd.read_csv(equity_path)
        st.line_chart(equity.set_index("date")["equity"])
    if trades_path.exists():
        st.dataframe(pd.read_csv(trades_path, dtype={"symbol": str}), use_container_width=True, hide_index=True)

with tabs[6]:
    trade_log = LOG_DIR / "trade_log.csv"
    watch_log = LOG_DIR / "watch_log.csv"
    risk_log = LOG_DIR / "risk_log.csv"
    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("交易")
        if trade_log.exists():
            st.dataframe(pd.read_csv(trade_log, dtype={"symbol": str}), use_container_width=True, hide_index=True)
    with col2:
        st.subheader("观察")
        if watch_log.exists():
            st.dataframe(pd.read_csv(watch_log, dtype={"symbol": str}), use_container_width=True, hide_index=True)
    with col3:
        st.subheader("风控")
        if risk_log.exists():
            st.dataframe(pd.read_csv(risk_log, dtype={"symbol": str}), use_container_width=True, hide_index=True)

with tabs[7]:
    watch_times = configured_watch_times()
    c1, c2, c3 = st.columns([1, 1, 1])
    auto_date = c1.date_input("刷新日期", value=date.today()).isoformat()
    auto_time = c2.selectbox("固定刷新时间", watch_times, index=min(1, len(watch_times) - 1))
    if c3.button("立即刷新实时行情", type="primary"):
        result = run_watch(auto_date, auto_time, source="auto")
        st.dataframe(result, use_container_width=True, hide_index=True)
    with st.expander("手动CSV兜底录入"):
        with st.form("snapshot_form"):
            c1, c2, c3, c4 = st.columns(4)
            snap_date = c1.date_input("快照日期", value=date.today()).isoformat()
            snap_time = c2.selectbox("时间", watch_times)
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
