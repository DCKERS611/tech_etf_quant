from __future__ import annotations

from pathlib import Path

from tech_etf_quant.uzi import create_uzi_task, get_uzi_status, run_uzi_analysis


def uzi_config(tmp_path: Path) -> dict:
    return {
        "enabled": True,
        "repo_url": "https://example.com/UZI-Skill.git",
        "local_path": str(tmp_path / "vendor" / "UZI-Skill"),
        "report_dir": str(tmp_path / "reports" / "uzi"),
        "default_depth": "lite",
        "python_executable": "python",
        "commands": {
            "quick-scan": {"label": "quick", "depth": "lite"},
            "dcf": {"label": "dcf", "depth": "deep"},
        },
    }


def test_uzi_status_is_project_local_and_not_installed(tmp_path):
    status = get_uzi_status(uzi_config(tmp_path))

    assert status.installed is False
    assert status.install_dir == str(tmp_path / "vendor" / "UZI-Skill")
    assert ".codex" not in status.install_dir


def test_create_uzi_task_writes_markdown_and_json(tmp_path):
    task = create_uzi_task("512480", command="quick-scan", config=uzi_config(tmp_path))

    assert task["scope"] == "project-local"
    assert task["slash_command"] == "/stock-deep-analyzer:quick-scan 512480"
    assert Path(task["json_path"]).exists()
    markdown = Path(task["markdown_path"]).read_text(encoding="utf-8")
    assert "vendor" in markdown
    assert "python" in markdown


def test_run_uzi_analysis_requires_project_repo(tmp_path):
    result = run_uzi_analysis("512480", command="dcf", config=uzi_config(tmp_path))

    assert result.ok is False
    assert "not installed" in result.message
    assert result.output_dir.startswith(str(tmp_path / "reports" / "uzi"))
