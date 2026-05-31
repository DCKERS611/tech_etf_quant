"""Command line interface."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .backtest import run_backtest
from .config import PROJECT_ROOT
from .data_loader import ensure_sample_data, latest_available_date, update_all_data
from .report import generate_daily_report
from .scoring import score_latest, save_ranking
from .uzi import (
    DEFAULT_UZI_CONFIG,
    UZI_DEPTHS,
    create_uzi_task,
    ensure_uzi_repo,
    get_uzi_status,
    run_uzi_analysis,
)
from .utils import init_project, setup_logging
from .watch import configured_watch_times, run_watch, snapshot_template

console = Console()


@click.group()
def main() -> None:
    """A-share technology ETF quant assistant."""


@main.command("init")
def init_cmd() -> None:
    """Initialize directories, config files and logs."""

    init_project()
    setup_logging()
    console.print("[green]Project initialized.[/green]")


@main.command("update-data")
@click.option("--start", "start_date", default="20200101", help="Start date, e.g. 20200101.")
@click.option("--end", "end_date", default=None, help="End date, e.g. 20260531.")
@click.option("--sample-only", is_flag=True, help="Generate deterministic local sample data without network calls.")
def update_data_cmd(start_date: str, end_date: str | None, sample_only: bool) -> None:
    """Download or update ETF daily data."""

    init_project()
    setup_logging()
    if sample_only:
        data = ensure_sample_data(start_date="2021-01-01", end_date=end_date, overwrite=True)
    else:
        data = update_all_data(start_date=start_date, end_date=end_date, use_fallback=True)
    console.print(f"[green]Updated {len(data)} ETF files.[/green]")


@main.command("score")
@click.option("--date", "target_date", default=None, help="Target date, YYYY-MM-DD.")
def score_cmd(target_date: str | None) -> None:
    """Calculate ETF scores and rankings."""

    init_project()
    data = ensure_sample_data() if target_date is None else None
    if target_date is None and data:
        target_date = latest_available_date(data)
    ranking = score_latest(target_date=target_date, save=True)
    target_date = target_date or (str(ranking["date"].max()) if not ranking.empty else "unknown")
    save_ranking(ranking, target_date)
    table = Table(title=f"ETF Ranking {target_date}")
    for col in ["rank_all", "symbol", "name", "group", "score", "trend_ok"]:
        table.add_column(col)
    for row in ranking.head(12).to_dict("records"):
        table.add_row(
            str(row["rank_all"]),
            str(row["symbol"]),
            str(row["name"]),
            str(row["group"]),
            f"{row['score']:.4f}",
            str(row["trend_ok"]),
        )
    console.print(table)


@main.command("report")
@click.option("--date", "target_date", required=True, help="Target date, YYYY-MM-DD.")
def report_cmd(target_date: str) -> None:
    """Generate daily Markdown and HTML reports."""

    init_project()
    paths = generate_daily_report(target_date)
    console.print(f"[green]Markdown:[/green] {paths['markdown']}")
    console.print(f"[green]HTML:[/green] {paths['html']}")


@main.command("watch")
@click.option("--date", "target_date", required=True, help="Target date, YYYY-MM-DD.")
@click.option("--time", "watch_time", required=True, help="Watch time, e.g. 10:35.")
@click.option("--snapshot", "snapshot_path", type=click.Path(path_type=Path), default=None)
@click.option(
    "--source",
    type=click.Choice(["auto", "manual"]),
    default="auto",
    show_default=True,
    help="auto pulls realtime data first; manual forces CSV fallback.",
)
def watch_cmd(target_date: str, watch_time: str, snapshot_path: Path | None, source: str) -> None:
    """Pull realtime intraday data and generate watch decisions."""

    init_project()
    result = run_watch(target_date, watch_time, snapshot_path, source=source)
    if result.empty:
        path = snapshot_template(snapshot_path)
        console.print(f"[yellow]Realtime/cache unavailable and no manual CSV rows. Template ready at {path}[/yellow]")
        return
    console.print(result.to_string(index=False))


@main.command("refresh-now")
@click.option("--date", "target_date", default=None, help="Target date, YYYY-MM-DD.")
@click.option("--time", "watch_time", default=None, help="Watch time, e.g. 10:35.")
@click.option("--skip-daily", is_flag=True, help="Only refresh intraday realtime data.")
def refresh_now_cmd(target_date: str | None, watch_time: str | None, skip_daily: bool) -> None:
    """Immediately refresh daily cache if requested, then refresh realtime watch data."""

    from datetime import date, datetime

    init_project()
    setup_logging()
    target_date = target_date or date.today().isoformat()
    watch_time = watch_time or datetime.now().strftime("%H:%M")
    if not skip_daily:
        update_all_data(end_date=target_date.replace("-", ""), use_fallback=True)
    result = run_watch(target_date, watch_time, source="auto")
    console.print(f"[green]Refresh completed at {target_date} {watch_time}.[/green]")
    console.print(f"Configured fixed refresh times: {', '.join(configured_watch_times())}")
    if result.empty:
        path = snapshot_template()
        console.print(f"[yellow]No realtime/cache/manual data available. Manual fallback template: {path}[/yellow]")
    else:
        console.print(result.head(20).to_string(index=False))


@main.command("backtest")
@click.option("--start", required=True, help="Start date, YYYY-MM-DD.")
@click.option("--end", required=True, help="End date, YYYY-MM-DD.")
def backtest_cmd(start: str, end: str) -> None:
    """Run full daily backtest."""

    init_project()
    result = run_backtest(start, end)
    performance = result["performance"]
    console.print("[green]Backtest completed.[/green]")
    console.print(performance)
    console.print(f"Output: {result['output_dir']}")


@main.command("uzi")
@click.option("--target", required=True, help="Stock or ETF target, e.g. 600519 or 512480.")
@click.option(
    "--command",
    "analysis_command",
    type=click.Choice(list(DEFAULT_UZI_CONFIG["commands"].keys())),
    default="quick-scan",
    show_default=True,
    help="Project-local UZI task command.",
)
@click.option("--depth", type=click.Choice(list(UZI_DEPTHS)), default=None, help="Override UZI depth.")
@click.option("--ensure", "ensure_repo", is_flag=True, help="Clone the UZI repo into vendor/UZI-Skill if missing.")
@click.option("--update", is_flag=True, help="Fast-forward update the local UZI repo.")
@click.option("--run", "run_now", is_flag=True, help="Run UZI run.py after creating the task.")
@click.option("--timeout", "timeout_seconds", default=1800, show_default=True, help="Run timeout in seconds.")
def uzi_cmd(
    target: str,
    analysis_command: str,
    depth: str | None,
    ensure_repo: bool,
    update: bool,
    run_now: bool,
    timeout_seconds: int,
) -> None:
    """Create or run a project-local UZI analysis task."""

    init_project()
    status = ensure_uzi_repo(update=update) if ensure_repo or update or run_now else get_uzi_status()
    if run_now:
        result = run_uzi_analysis(
            target=target,
            command=analysis_command,
            depth=depth,
            timeout_seconds=timeout_seconds,
        )
        console.print(f"[green]UZI run status:[/green] {result.message}")
        console.print(f"Output: {result.output_dir}")
        if result.stdout.strip():
            console.print(result.stdout[-4000:])
        if result.stderr.strip():
            console.print(f"[yellow]{result.stderr[-4000:]}[/yellow]")
        return

    task = create_uzi_task(target=target, command=analysis_command, depth=depth)
    table = Table(title="Project-local UZI")
    table.add_column("item")
    table.add_column("value")
    table.add_row("scope", "project-local")
    table.add_row("installed", str(status.installed))
    table.add_row("message", status.message)
    table.add_row("install_dir", status.install_dir)
    table.add_row("task", task["json_path"])
    table.add_row("slash_command", task["slash_command"])
    table.add_row("output_dir", task["output_dir"])
    console.print(table)
    if not status.installed:
        console.print("[yellow]Run again with --ensure or --run to clone vendor/UZI-Skill first.[/yellow]")


@main.command("dashboard")
def dashboard_cmd() -> None:
    """Start the local Streamlit dashboard."""

    init_project()
    app_path = PROJECT_ROOT / "app" / "streamlit_app.py"
    console.print("[green]Starting Streamlit dashboard on localhost...[/green]")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app_path),
            "--server.address",
            "localhost",
        ],
        check=False,
    )


if __name__ == "__main__":
    main()
