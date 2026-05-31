"""Project-local UZI-Skill integration."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .config import CONFIG_DIR, PROJECT_ROOT, REPORT_DIR

UZI_CONFIG_PATH = CONFIG_DIR / "uzi.yaml"
DEFAULT_UZI_CONFIG: dict[str, Any] = {
    "enabled": True,
    "repo_url": "https://github.com/wbh604/UZI-Skill.git",
    "local_path": "vendor/UZI-Skill",
    "report_dir": "reports/uzi",
    "default_depth": "lite",
    "python_executable": "",
    "commands": {
        "analyze-stock": {"label": "完整深度分析", "depth": "medium"},
        "quick-scan": {"label": "快速预判", "depth": "lite"},
        "scan-trap": {"label": "杀猪盘排查", "depth": "lite"},
        "dcf": {"label": "DCF估值专项", "depth": "deep"},
        "comps": {"label": "同行对标", "depth": "medium"},
        "lbo": {"label": "LBO压力测试", "depth": "deep"},
        "initiate": {"label": "机构首次覆盖", "depth": "deep"},
        "ic-memo": {"label": "投委会备忘录", "depth": "deep"},
        "investor-panel": {"label": "评审团投票", "depth": "lite"},
        "trap-detector": {"label": "风险排查", "depth": "lite"},
    },
}
UZI_DEPTHS = ("lite", "medium", "deep")


@dataclass(frozen=True)
class UziStatus:
    enabled: bool
    installed: bool
    repo_url: str
    install_dir: str
    report_dir: str
    current_commit: str
    message: str


@dataclass(frozen=True)
class UziRunResult:
    ok: bool
    command: list[str]
    output_dir: str
    stdout: str
    stderr: str
    returncode: int | None
    message: str


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _resolve_project_path(value: str | Path, default: Path) -> Path:
    if not value:
        return default
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_uzi_config(path: Path | None = None) -> dict[str, Any]:
    path = path or UZI_CONFIG_PATH
    if not path.exists():
        return dict(DEFAULT_UZI_CONFIG)
    with path.open("r", encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh) or {}
    return _deep_merge(DEFAULT_UZI_CONFIG, loaded)


def write_default_uzi_config(path: Path | None = None) -> Path:
    path = path or UZI_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(DEFAULT_UZI_CONFIG, fh, allow_unicode=True, sort_keys=False)
    return path


def uzi_install_dir(config: dict[str, Any] | None = None) -> Path:
    config = config or load_uzi_config()
    return _resolve_project_path(config.get("local_path", ""), PROJECT_ROOT / "vendor" / "UZI-Skill")


def uzi_report_dir(config: dict[str, Any] | None = None) -> Path:
    config = config or load_uzi_config()
    return _resolve_project_path(config.get("report_dir", ""), REPORT_DIR / "uzi")


def uzi_commands(config: dict[str, Any] | None = None) -> dict[str, dict[str, str]]:
    config = config or load_uzi_config()
    commands = config.get("commands") or {}
    return {str(key): dict(value or {}) for key, value in commands.items()}


def default_depth_for_command(command: str, config: dict[str, Any] | None = None) -> str:
    config = config or load_uzi_config()
    command_config = uzi_commands(config).get(command, {})
    depth = str(command_config.get("depth") or config.get("default_depth") or "lite")
    return depth if depth in UZI_DEPTHS else "lite"


def _git_commit(repo_dir: Path) -> str:
    if not (repo_dir / ".git").exists():
        return ""
    proc = subprocess.run(
        ["git", "-C", str(repo_dir), "rev-parse", "--short", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def get_uzi_status(config: dict[str, Any] | None = None) -> UziStatus:
    config = config or load_uzi_config()
    install_dir = uzi_install_dir(config)
    report_dir = uzi_report_dir(config)
    installed = (install_dir / "run.py").exists()
    commit = _git_commit(install_dir) if installed else ""
    if not config.get("enabled", True):
        message = "disabled"
    elif installed:
        message = "ready"
    else:
        message = "not installed"
    return UziStatus(
        enabled=bool(config.get("enabled", True)),
        installed=installed,
        repo_url=str(config.get("repo_url") or DEFAULT_UZI_CONFIG["repo_url"]),
        install_dir=str(install_dir),
        report_dir=str(report_dir),
        current_commit=commit,
        message=message,
    )


def ensure_uzi_repo(update: bool = False, config: dict[str, Any] | None = None) -> UziStatus:
    config = config or load_uzi_config()
    status = get_uzi_status(config)
    if not status.enabled:
        return status
    if shutil.which("git") is None:
        return UziStatus(
            enabled=status.enabled,
            installed=status.installed,
            repo_url=status.repo_url,
            install_dir=status.install_dir,
            report_dir=status.report_dir,
            current_commit=status.current_commit,
            message="git not found",
        )

    install_dir = Path(status.install_dir)
    if status.installed and not update:
        return status

    install_dir.parent.mkdir(parents=True, exist_ok=True)
    if status.installed:
        proc = subprocess.run(
            ["git", "-C", str(install_dir), "pull", "--ff-only"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    else:
        proc = subprocess.run(
            ["git", "clone", "--depth", "1", status.repo_url, str(install_dir)],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    refreshed = get_uzi_status(config)
    if proc.returncode != 0:
        return UziStatus(
            enabled=refreshed.enabled,
            installed=refreshed.installed,
            repo_url=refreshed.repo_url,
            install_dir=refreshed.install_dir,
            report_dir=refreshed.report_dir,
            current_commit=refreshed.current_commit,
            message=(proc.stderr or proc.stdout or "git command failed").strip(),
        )
    return refreshed


def _slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_.-]+", "_", value.strip()).strip("._-")
    return slug[:60] or "target"


def create_uzi_task(
    target: str,
    command: str = "quick-scan",
    depth: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or load_uzi_config()
    commands = uzi_commands(config)
    if command not in commands:
        raise ValueError(f"Unsupported UZI command: {command}")
    depth = depth or default_depth_for_command(command, config)
    if depth not in UZI_DEPTHS:
        raise ValueError(f"Unsupported UZI depth: {depth}")
    target = str(target).strip()
    if not target:
        raise ValueError("UZI target is required")

    status = get_uzi_status(config)
    report_dir = uzi_report_dir(config)
    report_dir.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now().strftime("%Y%m%d_%H%M%S")
    task_id = f"{created_at}_{_slug(command)}_{_slug(target)}"
    output_dir = report_dir / task_id
    slash_command = f"/stock-deep-analyzer:{command} {target}"
    python_executable = str(config.get("python_executable") or sys.executable)
    run_command = [
        python_executable,
        "run.py",
        target,
        "--depth",
        depth,
        "--no-browser",
        "--output-dir",
        str(output_dir),
    ]
    payload = {
        "schema": 1,
        "task_id": task_id,
        "created_at": created_at,
        "target": target,
        "command": command,
        "command_label": commands[command].get("label", command),
        "depth": depth,
        "slash_command": slash_command,
        "run_command": run_command,
        "repo_url": status.repo_url,
        "install_dir": status.install_dir,
        "repo_installed": status.installed,
        "output_dir": str(output_dir),
        "scope": "project-local",
        "disclaimer": "个人学习用途，不作为投资参考。",
    }
    json_path = report_dir / f"{task_id}.json"
    md_path = report_dir / f"{task_id}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_task_markdown(payload), encoding="utf-8")
    return {
        **payload,
        "json_path": str(json_path),
        "markdown_path": str(md_path),
    }


def _render_task_markdown(payload: dict[str, Any]) -> str:
    command_line = " ".join(f'"{part}"' if " " in part else part for part in payload["run_command"])
    return "\n".join(
        [
            f"# UZI Project Task {payload['task_id']}",
            "",
            "> 个人学习用途，不作为投资参考。",
            "",
            f"- Target: `{payload['target']}`",
            f"- Command: `{payload['slash_command']}`",
            f"- Depth: `{payload['depth']}`",
            f"- Scope: `{payload['scope']}`",
            f"- Installed: `{payload['repo_installed']}`",
            f"- Install dir: `{payload['install_dir']}`",
            f"- Output dir: `{payload['output_dir']}`",
            "",
            "```powershell",
            f"cd {payload['install_dir']}",
            command_line,
            "```",
            "",
        ]
    )


def run_uzi_analysis(
    target: str,
    command: str = "quick-scan",
    depth: str | None = None,
    timeout_seconds: int = 1800,
    config: dict[str, Any] | None = None,
) -> UziRunResult:
    config = config or load_uzi_config()
    task = create_uzi_task(target=target, command=command, depth=depth, config=config)
    status = get_uzi_status(config)
    if not status.installed:
        return UziRunResult(
            ok=False,
            command=task["run_command"],
            output_dir=task["output_dir"],
            stdout="",
            stderr="",
            returncode=None,
            message="UZI repo is not installed in this project. Run ensure_uzi_repo first.",
        )

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("UZI_CLI_ONLY", "1")
    env.setdefault("UZI_NO_AUTO_OPEN", "1")
    env.setdefault("UZI_NO_UPDATE_CHECK", "1")
    env["UZI_DEPTH"] = task["depth"]
    output_dir = Path(task["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            task["run_command"],
            cwd=status.install_dir,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        return UziRunResult(
            ok=False,
            command=task["run_command"],
            output_dir=str(output_dir),
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            returncode=None,
            message=f"timeout after {timeout_seconds} seconds",
        )
    except OSError as exc:
        return UziRunResult(
            ok=False,
            command=task["run_command"],
            output_dir=str(output_dir),
            stdout="",
            stderr=str(exc),
            returncode=None,
            message="failed to start UZI runner",
        )
    return UziRunResult(
        ok=proc.returncode == 0,
        command=task["run_command"],
        output_dir=str(output_dir),
        stdout=proc.stdout,
        stderr=proc.stderr,
        returncode=proc.returncode,
        message="completed" if proc.returncode == 0 else "failed",
    )


def status_as_dict(status: UziStatus) -> dict[str, Any]:
    return asdict(status)
