"""Pytest configuration for ensuring project imports work everywhere."""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_repo_root_on_path() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    str_root = str(repo_root)
    if str_root not in sys.path:
        sys.path.insert(0, str_root)


_ensure_repo_root_on_path()
