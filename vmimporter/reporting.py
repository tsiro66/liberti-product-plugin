"""Logging and import reporting."""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class ImportSummary:
    total_rows: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    failed: int = 0
    validation_errors: int = 0
    database_errors: int = 0
    missing_images: int = 0
    images_copied: int = 0
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            "=" * 62,
            "IMPORT SUMMARY",
            "=" * 62,
            f"CSV rows processed : {self.total_rows}",
            f"created            : {self.created}",
            f"updated            : {self.updated}",
            f"unchanged          : {self.unchanged}",
            f"skipped            : {self.skipped}",
            f"failed             : {self.failed}",
            f"images copied      : {self.images_copied}",
            f"missing images     : {self.missing_images} (skipped products affected: see log)",
            f"validation errors  : {self.validation_errors}",
            f"database errors    : {self.database_errors}",
        ]
        if self.failures:
            lines.append("-" * 62)
            lines.append("Failures:")
            lines.extend(f"  - {f}" for f in self.failures)
        if self.warnings:
            lines.append("-" * 62)
            lines.append("Warnings:")
            lines.extend(f"  - {w}" for w in self.warnings)
        lines.append("=" * 62)
        return "\n".join(lines)


def setup_logging(log_dir: str, verbose: bool = False) -> Path:
    """Console INFO (DEBUG with --verbose) + full DEBUG log file."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    logfile = log_path / f"import-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.log"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(logging.Formatter("%(levelname)-7s %(message)s"))
    root.addHandler(console)

    filehandler = logging.FileHandler(logfile, encoding="utf-8")
    filehandler.setLevel(logging.DEBUG)
    filehandler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    root.addHandler(filehandler)
    return logfile
