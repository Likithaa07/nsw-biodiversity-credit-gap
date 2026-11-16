"""Shared paths, logging and data checks used by every script in the pipeline."""
# STEP 1: Imports and default folders
from __future__ import annotations

import logging
import sys
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
OUTPUTS = ROOT / "outputs"


# STEP 2: Logging - one consistent format for every script
def get_logger(name: str) -> logging.Logger:
    """Return a logger. The first call sets up a simple 'time  level  message' format."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                            format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
                            datefmt="%H:%M:%S")
    return logging.getLogger(name)


# STEP 3: Errors that stop the pipeline with a clear message
class PipelineError(Exception):
    """Base class for problems that should stop the pipeline."""


class MissingInputError(PipelineError, FileNotFoundError):
    """An input file is missing."""


class DataValidationError(PipelineError, ValueError):
    """The data failed a quality check."""


def require_files(*paths: Path, hint: str = "") -> None:
    """Stop with a helpful message if any input file is missing."""
    missing = [str(p) for p in paths if not Path(p).is_file()]
    if missing:
        message = "Missing input file(s):\n  " + "\n  ".join(missing)
        if hint:
            message += f"\n{hint}"
        raise MissingInputError(message)


# STEP 4: Data checks - each one raises DataValidationError when it fails
def require_columns(df: pd.DataFrame, columns: Iterable[str], name: str) -> None:
    """Check that a table has every column the next steps rely on."""
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise DataValidationError(
            f"{name}: missing column(s) {missing}. The register export format may have changed.")


def require_min_rows(df: pd.DataFrame, minimum: int, name: str) -> None:
    """Check that a table is not empty or suspiciously small."""
    if len(df) < minimum:
        raise DataValidationError(
            f"{name}: only {len(df):,} rows (expected at least {minimum:,}). "
            "The export may be incomplete.")


def require_unique(df: pd.DataFrame, column: str, name: str) -> None:
    """Check that a column has no duplicate values."""
    dupes = int(df[column].duplicated().sum())
    if dupes:
        raise DataValidationError(f"{name}: {dupes:,} duplicate values in '{column}'.")


def require_in_range(values: pd.Series, name: str, low: float | None = None,
                     high: float | None = None) -> None:
    """Check that every non-missing value lies between low and high (inclusive)."""
    v = values.dropna()
    bad = pd.Series(False, index=v.index)
    if low is not None:
        bad |= v < low
    if high is not None:
        bad |= v > high
    if bad.any():
        raise DataValidationError(
            f"{name}: {int(bad.sum()):,} values outside [{low}, {high}] "
            f"(e.g. {v[bad].iloc[0]}).")


def require_share_not_null(values: pd.Series, name: str, minimum_share: float) -> None:
    """Check that at least a given share of values is filled in."""
    share = values.notna().mean() if len(values) else 0.0
    if share < minimum_share:
        raise DataValidationError(
            f"{name}: only {share:.0%} filled in (expected at least {minimum_share:.0%}).")
