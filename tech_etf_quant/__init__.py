"""Import bridge for running `python -m tech_etf_quant.cli` from the repo root."""

from __future__ import annotations

from pathlib import Path

__version__ = "1.0.0"

_SRC_PACKAGE = Path(__file__).resolve().parents[1] / "src" / "tech_etf_quant"
if _SRC_PACKAGE.exists():
    __path__.append(str(_SRC_PACKAGE))
