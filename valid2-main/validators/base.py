from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Optional
import pandas as pd


LogCallback = Optional[Callable[[str], None]]


@dataclass
class ValidationResult:
    """Common result contract consumed by the UI."""
    name: str
    output_file: str
    records: int = 0
    passed: int = 0
    failed: int = 0
    match_pct: float = 0.0
    details: Dict[str, object] = field(default_factory=dict)

    @property
    def summary(self) -> dict:
        return {
            "Records": self.records,
            "Passed": self.passed,
            "Failed": self.failed,
            "Match %": round(self.match_pct, 2),
        }


def log(callback: LogCallback, message: str) -> None:
    if callback:
        callback(str(message))


def require_files(files: Dict[str, str], required: list[str]) -> None:
    missing = [name for name in required if not files.get(name)]
    if missing:
        raise ValueError("Missing required file(s): " + ", ".join(missing))

    for name in required:
        path = Path(files[name])
        if not path.exists():
            raise FileNotFoundError(f"{name} not found: {path}")


def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.astype(str).str.strip()
    return df


def write_frames(output_file: Path, frames: Dict[str, pd.DataFrame]) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        for sheet, frame in frames.items():
            frame.to_excel(writer, sheet_name=sheet[:31], index=False)
