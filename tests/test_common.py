"""Tests for the shared data checks in common.py."""
# STEP 1: Imports
import pandas as pd
import pytest

from common import (DataValidationError, MissingInputError, require_columns, require_files,
                    require_in_range, require_min_rows, require_share_not_null, require_unique)


# STEP 2: Missing files stop the pipeline with a clear message
def test_require_files_lists_missing_file(tmp_path):
    with pytest.raises(MissingInputError, match="Supply.xls"):
        require_files(tmp_path / "Supply.xls", hint="Download it first.")


def test_require_files_passes_when_present(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("x")
    require_files(f)


# STEP 3: Each data check raises DataValidationError when it fails
def test_require_columns():
    df = pd.DataFrame({"a": [1]})
    require_columns(df, ["a"], "t")
    with pytest.raises(DataValidationError, match="'b'"):
        require_columns(df, ["a", "b"], "t")


def test_require_min_rows():
    with pytest.raises(DataValidationError, match="only 1 rows"):
        require_min_rows(pd.DataFrame({"a": [1]}), 10, "t")


def test_require_unique():
    with pytest.raises(DataValidationError, match="1 duplicate"):
        require_unique(pd.DataFrame({"id": [1, 1, 2]}), "id", "t")


def test_require_in_range_ignores_missing_values():
    require_in_range(pd.Series([0, 5, None]), "x", low=0, high=5)
    with pytest.raises(DataValidationError, match="outside"):
        require_in_range(pd.Series([-1, 5]), "x", low=0)


def test_require_share_not_null():
    require_share_not_null(pd.Series([1, 2, None, 4]), "x", 0.75)
    with pytest.raises(DataValidationError, match="50%"):
        require_share_not_null(pd.Series([1, None]), "x", 0.9)
