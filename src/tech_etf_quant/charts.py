"""Chart generation for daily ranking and backtest outputs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import CHART_DIR


def _use_matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    for font_name in ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Arial Unicode MS"]:
        if font_name in available_fonts:
            plt.rcParams["font.sans-serif"] = [font_name]
            break
    plt.rcParams["axes.unicode_minus"] = False

    return plt


def generate_equity_curve_chart(equity_curve: pd.DataFrame, output_dir: Path | None = None) -> Path | None:
    if equity_curve.empty:
        return None
    output_dir = output_dir or CHART_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    plt = _use_matplotlib()
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(pd.to_datetime(equity_curve["date"]), equity_curve["equity"], color="#2563eb", linewidth=1.8)
    ax.set_title("Equity Curve")
    ax.set_xlabel("Date")
    ax.set_ylabel("Equity")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    path = output_dir / "equity_curve.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def generate_drawdown_chart(equity_curve: pd.DataFrame, output_dir: Path | None = None) -> Path | None:
    if equity_curve.empty:
        return None
    output_dir = output_dir or CHART_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    plt = _use_matplotlib()
    fig, ax = plt.subplots(figsize=(10, 3.5))
    ax.fill_between(pd.to_datetime(equity_curve["date"]), equity_curve["drawdown"], 0, color="#dc2626", alpha=0.35)
    ax.set_title("Drawdown")
    ax.set_xlabel("Date")
    ax.set_ylabel("Drawdown")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    path = output_dir / "drawdown_curve.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def generate_ranking_bar_chart(ranking: pd.DataFrame, output_dir: Path | None = None) -> Path | None:
    if ranking.empty:
        return None
    output_dir = output_dir or CHART_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    top = ranking[ranking["group"] != "benchmark"].head(12).copy()
    if top.empty:
        top = ranking.head(12).copy()
    plt = _use_matplotlib()
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(top["symbol"] + " " + top["name"], top["score"], color="#0f766e")
    ax.invert_yaxis()
    ax.set_title("ETF Score Ranking")
    ax.set_xlabel("Score")
    fig.tight_layout()
    path = output_dir / "ranking_bar.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def generate_position_chart(positions: pd.DataFrame, output_dir: Path | None = None) -> Path | None:
    if positions.empty:
        return None
    output_dir = output_dir or CHART_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    pivot = positions.pivot_table(index="date", columns="symbol", values="market_value", aggfunc="sum").fillna(0)
    plt = _use_matplotlib()
    fig, ax = plt.subplots(figsize=(10, 4))
    pivot.plot.area(ax=ax, alpha=0.75)
    ax.set_title("Position Value")
    ax.set_xlabel("Date")
    ax.set_ylabel("Market Value")
    fig.tight_layout()
    path = output_dir / "positions_area.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def generate_group_heatmap(ranking: pd.DataFrame, output_dir: Path | None = None) -> Path | None:
    if ranking.empty:
        return None
    output_dir = output_dir or CHART_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        import plotly.express as px

        data = ranking.pivot_table(index="group", columns="symbol", values="score", aggfunc="mean").fillna(0)
        fig = px.imshow(data, aspect="auto", color_continuous_scale="RdYlGn", title="Group Strength Heatmap")
        path = output_dir / "group_heatmap.html"
        fig.write_html(path)
        return path
    except Exception:
        return None


def generate_trade_points_chart(trades: pd.DataFrame, output_dir: Path | None = None) -> Path | None:
    if trades.empty:
        return None
    output_dir = output_dir or CHART_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        import plotly.express as px

        fig = px.scatter(
            trades,
            x="date",
            y="price",
            color="side",
            symbol="side",
            hover_data=["symbol", "name", "shares", "amount", "reason"],
            title="Trade Records",
        )
        path = output_dir / "trade_points.html"
        fig.write_html(path)
        return path
    except Exception:
        return None


def generate_backtest_charts(
    equity_curve: pd.DataFrame,
    trades: pd.DataFrame,
    positions: pd.DataFrame | None = None,
    output_dir: Path | None = None,
) -> list[Path]:
    output_dir = output_dir or CHART_DIR
    paths = [
        generate_equity_curve_chart(equity_curve, output_dir),
        generate_drawdown_chart(equity_curve, output_dir),
        generate_position_chart(positions, output_dir) if positions is not None else None,
        generate_trade_points_chart(trades, output_dir),
    ]
    return [path for path in paths if path is not None]


def generate_daily_charts(ranking: pd.DataFrame, output_dir: Path | None = None) -> list[Path]:
    output_dir = output_dir or CHART_DIR
    paths = [
        generate_ranking_bar_chart(ranking, output_dir),
        generate_group_heatmap(ranking, output_dir),
    ]
    return [path for path in paths if path is not None]
