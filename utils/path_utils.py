from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "DataValidationHub"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def project_root() -> Path:
    """Return the source project root or executable directory when packaged."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def app_data_dir() -> Path:
    """Return a writable per-user application directory on Windows."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        path = base / APP_NAME
    else:
        path = Path.home() / f".{APP_NAME.lower()}"
    path.mkdir(parents=True, exist_ok=True)
    return path


# Reports/logs should be writable even when the EXE is installed under Program Files.
OUTPUT_DIR = app_data_dir() / "outputs"
LOG_DIR = app_data_dir() / "logs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


def file_name(path: str) -> str:
    return Path(path).name
