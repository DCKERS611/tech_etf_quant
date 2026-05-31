"""Daily multi-ETF backtest engine."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from .broker_sim import Trade, execute_buy, execute_sell
from .charts import generate_backtest_charts
from .config import BACKTEST_REPORT_DIR, Settings, load_etf_pool, load_settings
from .data_loader import ensure_sample_data, load_processed_data
from .indicators import add_indicators
from .portfolio import Portfolio
from .risk import check_position_stop_loss, evaluate_trade_permission, log_account_risk_if_needed
from .scoring import calculate_scores
from .strategy import StrategySignal, pick_primary_signal


def _normalize_data(data_by_symbol: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for symbol, df in data_by_symbol.items():
        if df.empty:
            continue
        work = df.copy()
        work["symbol"] = str(symbol).zfill(6)
        work["date"] = pd.to_datetime(work["date"]).dt.strftime("%Y-%m-%d")
        if "ma20" not in work.columns:
            work = add_indicators(work)
        out[str(symbol).zfill(6)] = work.sort_values("date").reset_index(drop=True)
    return out


def _dates_between(data_by_symbol: dict[str, pd.DataFrame], start: str, end: str) -> list[str]:
    dates: set[str] = set()
    for df in data_by_symbol.values():
        dates.update(df.loc[(df["date"] >= start) & (df["date"] <= end), "date"].dropna().astype(str).tolist())
    return sorted(dates)


def _row_on_date(df: pd.DataFrame, date_value: str) -> pd.Series | None:
    rows = df[df["date"] == date_value]
    if rows.empty:
        return None
    return rows.iloc[-1]


def _latest_rows(data_by_symbol: dict[str, pd.DataFrame], date_value: str) -> dict[str, pd.Series]:
    rows: dict[str, pd.Series] = {}
    for symbol, df in data_by_symbol.items():
        part = df[df["date"] <= date_value]
        if not part.empty:
            rows[symbol] = part.iloc[-1]
    return rows


def _position_state(portfolio: Portfolio) -> str:
    if not portfolio.positions:
        return "EMPTY"
    types = {pos.position_type for pos in portfolio.positions.values()}
    if "STRONG" in types:
        return "STRONG"
    if "MAIN" in types:
        return "MAIN"
    return "TEST_ONLY"


def _benchmark_return(data_by_symbol: dict[str, pd.DataFrame], symbol: str, start: str, end: str) -> float:
    df = data_by_symbol.get(symbol)
    if df is None or df.empty:
        return 0.0
    part = df[(df["date"] >= start) & (df["date"] <= end)]
    if len(part) < 2:
        return 0.0
    first = float(part.iloc[0]["close"])
    last = float(part.iloc[-1]["close"])
    return last / first - 1 if first > 0 else 0.0


def calculate_performance(
    equity_curve: pd.DataFrame,
    trades: pd.DataFrame,
    data_by_symbol: dict[str, pd.DataFrame],
    initial_cash: float,
    start: str,
    end: str,
) -> dict:
    if equity_curve.empty:
        return {}
    equity = equity_curve["equity"].astype(float)
    returns = equity.pct_change().fillna(0)
    cumulative = equity.iloc[-1] / initial_cash - 1
    n = max(len(equity_curve), 1)
    annualized = (1 + cumulative) ** (252 / n) - 1 if cumulative > -1 else -1
    max_drawdown = float(equity_curve["drawdown"].min())
    sharpe = float(np.sqrt(252) * returns.mean() / returns.std()) if returns.std() > 0 else 0.0
    downside = returns[returns < 0]
    sortino = float(np.sqrt(252) * returns.mean() / downside.std()) if len(downside) > 1 and downside.std() > 0 else 0.0
    annualized_vol = float(returns.std() * np.sqrt(252)) if returns.std() > 0 else 0.0
    calmar = float(annualized / abs(max_drawdown)) if max_drawdown < 0 else 0.0
    sell_trades = trades[trades["side"] == "SELL"] if not trades.empty else pd.DataFrame()
    wins = sell_trades[sell_trades.get("realized_pnl", 0) > 0] if not sell_trades.empty else pd.DataFrame()
    losses = sell_trades[sell_trades.get("realized_pnl", 0) < 0] if not sell_trades.empty else pd.DataFrame()
    avg_profit = float(wins["realized_pnl"].mean()) if not wins.empty else 0.0
    avg_loss = float(losses["realized_pnl"].mean()) if not losses.empty else 0.0
    state_counts = equity_curve["position_state"].value_counts(normalize=True).to_dict()
    exposure = (
        (equity_curve["position_value"].astype(float) / equity_curve["equity"].replace(0, np.nan).astype(float))
        .fillna(0)
        .clip(lower=0)
    )
    total_turnover = float(trades["amount"].sum() / initial_cash) if not trades.empty and "amount" in trades else 0.0
    fee_drag = float(trades["commission"].sum() / initial_cash) if not trades.empty and "commission" in trades else 0.0
    slippage_drag = float(trades["slippage"].sum() / initial_cash) if not trades.empty and "slippage" in trades else 0.0
    max_consecutive_losses = 0
    cur_losses = 0
    holding_days: list[int] = []
    open_dates: dict[str, list[pd.Timestamp]] = {}
    if not sell_trades.empty:
        for _, trade in trades.sort_values(["date", "side"]).iterrows():
            symbol = str(trade["symbol"])
            if trade["side"] == "BUY":
                open_dates.setdefault(symbol, []).append(pd.to_datetime(trade["date"]))
            elif trade["side"] == "SELL" and open_dates.get(symbol):
                buy_date = open_dates[symbol].pop(0)
                holding_days.append(max((pd.to_datetime(trade["date"]) - buy_date).days, 0))
            pnl = float(trade.get("realized_pnl", 0) or 0)
            if trade["side"] == "SELL" and pnl < 0:
                cur_losses += 1
                max_consecutive_losses = max(max_consecutive_losses, cur_losses)
            elif trade["side"] == "SELL":
                cur_losses = 0
    return {
        "cumulative_return": float(cumulative),
        "annualized_return": float(annualized),
        "max_drawdown": max_drawdown,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "annualized_volatility": annualized_vol,
        "calmar_ratio": calmar,
        "trade_count": int(len(trades)),
        "win_rate": float(len(wins) / len(sell_trades)) if len(sell_trades) else 0.0,
        "average_profit": avg_profit,
        "average_loss": avg_loss,
        "profit_loss_ratio": float(avg_profit / abs(avg_loss)) if avg_loss < 0 else 0.0,
        "max_single_loss": float(sell_trades["realized_pnl"].min()) if not sell_trades.empty else 0.0,
        "max_consecutive_losses": int(max_consecutive_losses),
        "average_holding_days": float(np.mean(holding_days)) if holding_days else 0.0,
        "empty_days_ratio": float(state_counts.get("EMPTY", 0.0)),
        "test_only_days_ratio": float(state_counts.get("TEST_ONLY", 0.0)),
        "main_days_ratio": float(state_counts.get("MAIN", 0.0)),
        "strong_days_ratio": float(state_counts.get("STRONG", 0.0)),
        "average_exposure": float(exposure.mean()),
        "max_exposure": float(exposure.max()),
        "turnover": total_turnover,
        "fee_drag": fee_drag,
        "slippage_drag": slippage_drag,
        "data_days": int(len(equity_curve)),
        "execution_model": "next_open_with_slippage_commission_lot_size",
        "lookahead_guard": "signals generated after close, orders executed next open",
        "relative_588000": float(cumulative - _benchmark_return(data_by_symbol, "588000", start, end)),
        "relative_159915": float(cumulative - _benchmark_return(data_by_symbol, "159915", start, end)),
        "relative_510300": float(cumulative - _benchmark_return(data_by_symbol, "510300", start, end)),
    }


def _write_html_report(output_dir: Path, performance: dict, equity_curve: pd.DataFrame, trades: pd.DataFrame) -> Path:
    rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in performance.items())
    html = f"""
<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>Backtest Report</title></head>
<body>
<h1>A股科技ETF量化系统回测报告</h1>
<h2>绩效指标</h2>
<table border="1" cellspacing="0" cellpadding="6">{rows}</table>
<h2>最近净值</h2>
{equity_curve.tail(20).to_html(index=False)}
<h2>最近交易</h2>
{trades.tail(30).to_html(index=False) if not trades.empty else "<p>暂无交易</p>"}
</body>
</html>
"""
    path = output_dir / "backtest_report.html"
    path.write_text(html, encoding="utf-8")
    return path


def run_backtest(
    start: str,
    end: str,
    data_by_symbol: dict[str, pd.DataFrame] | None = None,
    etf_pool: pd.DataFrame | None = None,
    settings: Settings | None = None,
    output_dir: Path | None = None,
    write_outputs: bool = True,
) -> dict[str, object]:
    settings = settings or load_settings()
    output_dir = output_dir or BACKTEST_REPORT_DIR
    if data_by_symbol is None:
        data_by_symbol = load_processed_data()
        if not data_by_symbol:
            data_by_symbol = ensure_sample_data(end_date=end)
    data_by_symbol = _normalize_data(data_by_symbol)
    etf_pool = etf_pool if etf_pool is not None else load_etf_pool(enabled_only=True)
    pool_lookup = etf_pool.set_index("symbol").to_dict("index")
    dates = _dates_between(data_by_symbol, start, end)
    initial_cash = float(settings.get("account.initial_cash", 8000))
    portfolio = Portfolio(cash=initial_cash, max_equity=initial_cash)
    pending_orders: list[dict] = []
    trades: list[Trade] = []
    equity_rows: list[dict] = []
    position_rows: list[dict] = []
    signal_rows: list[dict] = []

    for i, current_date in enumerate(dates):
        open_prices = {
            symbol: float(row["open"])
            for symbol, df in data_by_symbol.items()
            if (row := _row_on_date(df, current_date)) is not None and pd.notna(row.get("open"))
        }
        close_rows = {
            symbol: row
            for symbol, df in data_by_symbol.items()
            if (row := _row_on_date(df, current_date)) is not None
        }
        for order in pending_orders:
            symbol = order["symbol"]
            if symbol not in open_prices:
                continue
            if order["side"] == "BUY":
                if symbol not in portfolio.positions and len(portfolio.positions) >= 2:
                    continue
                trade = execute_buy(
                    portfolio,
                    symbol,
                    order["name"],
                    open_prices[symbol],
                    order["amount"],
                    current_date,
                    position_type=order["position_type"],
                    reason=order["reason"],
                    signal_type=order["signal_type"],
                    settings=settings,
                )
            else:
                if not portfolio.can_sell(symbol, current_date):
                    continue
                trade = execute_sell(
                    portfolio,
                    symbol,
                    open_prices[symbol],
                    current_date,
                    reason=order["reason"],
                    signal_type=order["signal_type"],
                    settings=settings,
                )
            if trade is not None:
                trades.append(trade)
        pending_orders = []
        close_prices = {symbol: float(row["close"]) for symbol, row in close_rows.items() if pd.notna(row.get("close"))}
        portfolio.update_market_prices(close_prices)
        log_account_risk_if_needed(current_date, portfolio, settings)
        equity_rows.append(
            {
                "date": current_date,
                "cash": portfolio.cash,
                "position_value": portfolio.position_value,
                "equity": portfolio.equity,
                "drawdown": portfolio.drawdown,
                "risk_state": portfolio.risk_state,
                "position_state": _position_state(portfolio),
            }
        )
        for pos in portfolio.positions.values():
            position_rows.append(
                {
                    "date": current_date,
                    "symbol": pos.symbol,
                    "name": pos.name,
                    "shares": pos.shares,
                    "avg_cost": pos.avg_cost,
                    "last_price": pos.last_price,
                    "market_value": pos.market_value,
                    "unrealized_pnl": pos.unrealized_pnl,
                    "unrealized_pnl_ratio": pos.unrealized_pnl_ratio,
                    "position_type": pos.position_type,
                }
            )
        if i >= len(dates) - 1:
            continue
        for symbol, pos in list(portfolio.positions.items()):
            row = close_rows.get(symbol)
            if row is None:
                continue
            close = float(row["close"])
            trend_break = (pd.notna(row.get("ma20")) and close < float(row["ma20"]) * 0.985) or not bool(
                row.get("trend_ok", False)
            )
            if check_position_stop_loss(pos, close, settings):
                pending_orders.append(
                    {
                        "side": "SELL",
                        "symbol": symbol,
                        "name": pos.name,
                        "signal_type": "SELL",
                        "position_type": pos.position_type,
                        "amount": 0,
                        "reason": "触发单笔止损",
                    }
                )
            elif trend_break and portfolio.can_sell(symbol, dates[i + 1]):
                pending_orders.append(
                    {
                        "side": "SELL",
                        "symbol": symbol,
                        "name": pos.name,
                        "signal_type": "REDUCE",
                        "position_type": pos.position_type,
                        "amount": 0,
                        "reason": "趋势破坏或跌破MA20",
                    }
                )
        if len(portfolio.positions) < 2 and not any(order["side"] == "BUY" for order in pending_orders):
            ranking = calculate_scores(data_by_symbol, etf_pool=etf_pool, target_date=current_date, settings=settings)
            if not ranking.empty:
                market_rows = _latest_rows(data_by_symbol, current_date)
                top = ranking[ranking["group"] != "benchmark"].iloc[0]
                risk = evaluate_trade_permission(
                    portfolio,
                    pct_change=float(top.get("pct_change", 0) or 0),
                    high_open_gap=0.0,
                    watch_time="14:30",
                    settings=settings,
                )
                signal = pick_primary_signal(ranking, risk, market_rows=market_rows, settings=settings)
                if signal is not None and signal.signal_type == "HOLD" and len(portfolio.positions) == 0:
                    signal = StrategySignal(
                        date=signal.date,
                        symbol=str(top["symbol"]),
                        name=str(top["name"]),
                        signal_type="BUY_TEST",
                        position_type="TEST",
                        suggested_amount=float(settings.get("account.test_position_amount", 1000)),
                        suggested_time="14:30",
                        stop_loss_price=float(top["close"]) * 0.95,
                        reason="无主仓机会时保留测试仓参与",
                    )
                if signal is not None:
                    signal_rows.append(
                        {
                            "date": current_date,
                            "symbol": signal.symbol,
                            "name": signal.name,
                            "signal_type": signal.signal_type,
                            "position_type": signal.position_type,
                            "suggested_amount": signal.suggested_amount,
                            "suggested_time": signal.suggested_time,
                            "stop_loss_price": signal.stop_loss_price,
                            "reason": signal.reason,
                            "invalid_condition": signal.invalid_condition,
                            "next_execution_date": dates[i + 1],
                        }
                    )
                if signal is not None and signal.signal_type.startswith("BUY") and signal.symbol not in portfolio.positions:
                    pending_orders.append(
                        {
                            "side": "BUY",
                            "symbol": signal.symbol,
                            "name": signal.name,
                            "signal_type": signal.signal_type,
                            "position_type": signal.position_type,
                            "amount": signal.suggested_amount,
                            "reason": signal.reason,
                        }
                    )

    equity_curve = pd.DataFrame(equity_rows)
    trades_df = pd.DataFrame([asdict(trade) for trade in trades])
    positions_df = pd.DataFrame(position_rows)
    signals_df = pd.DataFrame(signal_rows)
    performance = calculate_performance(equity_curve, trades_df, data_by_symbol, initial_cash, start, end)
    performance["signal_count"] = int(len(signals_df))
    if write_outputs:
        output_dir.mkdir(parents=True, exist_ok=True)
        equity_curve.to_csv(output_dir / "equity_curve.csv", index=False, encoding="utf-8")
        trades_df.to_csv(output_dir / "trades.csv", index=False, encoding="utf-8")
        positions_df.to_csv(output_dir / "positions.csv", index=False, encoding="utf-8")
        signals_df.to_csv(output_dir / "signals.csv", index=False, encoding="utf-8")
        (output_dir / "performance.json").write_text(
            json.dumps(performance, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _write_html_report(output_dir, performance, equity_curve, trades_df)
        generate_backtest_charts(equity_curve, trades_df, positions_df)
    return {
        "portfolio": portfolio,
        "equity_curve": equity_curve,
        "trades": trades_df,
        "positions": positions_df,
        "signals": signals_df,
        "performance": performance,
        "output_dir": output_dir,
    }
