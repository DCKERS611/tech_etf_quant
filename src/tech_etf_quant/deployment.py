"""Streamlit Cloud deployment health checks."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .config import DEPLOY_REPORT_DIR, PROJECT_ROOT


@dataclass(frozen=True)
class DeployCheck:
    name: str
    ok: bool
    message: str


def _contains(path: Path, text: str) -> bool:
    return path.exists() and text in path.read_text(encoding="utf-8", errors="ignore")


def run_deploy_health_check(output_dir: Path | None = None) -> dict:
    output_dir = output_dir or DEPLOY_REPORT_DIR
    main_file = PROJECT_ROOT / "app" / "streamlit_app.py"
    requirements = PROJECT_ROOT / "requirements.txt"
    pyproject = PROJECT_ROOT / "pyproject.toml"
    uv_lock = PROJECT_ROOT / "uv.lock"
    checks = [
        DeployCheck("main_file", main_file.exists(), "Main file path should be app/streamlit_app.py"),
        DeployCheck("requirements", requirements.exists(), "requirements.txt is present"),
        DeployCheck("streamlit_dependency", _contains(requirements, "streamlit"), "streamlit dependency is pinned"),
        DeployCheck("akshare_dependency", _contains(requirements, "akshare"), "akshare dependency is pinned"),
        DeployCheck("pyyaml_dependency", _contains(requirements, "pyyaml"), "pyyaml dependency is pinned"),
        DeployCheck("no_uv_lock", not uv_lock.exists(), "uv.lock is absent for Streamlit Cloud installer stability"),
        DeployCheck("src_layout", _contains(pyproject, 'package-dir = {"" = "src"}'), "pyproject uses src package layout"),
        DeployCheck("package_false", _contains(pyproject, "package = false"), "uv package mode is disabled"),
    ]
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "main_file_path": "app/streamlit_app.py",
        "status": "pass" if all(check.ok for check in checks) else "warn",
        "checks": [asdict(check) for check in checks],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "streamlit_health.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
