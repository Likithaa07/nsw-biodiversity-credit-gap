"""Tests for the cleaning steps in clean.py."""
# STEP 1: Imports
import pandas as pd

from clean import QualityLog, clean_text, simplify, tidy_columns, to_dates


# STEP 2: Column names and name matching
def test_tidy_columns():
    df = pd.DataFrame(columns=[" Credit ID ", "Price per credit (ex GST)"])
    assert list(tidy_columns(df).columns) == ["credit_id", "price_per_credit_ex_gst"]


def test_simplify_matches_different_spellings():
    names = pd.Series(["Blakely's Red Gum - woodland", "Blakelys Red Gum woodland"])
    assert simplify(names).nunique() == 1


# STEP 3: Text cleaning and the quality log
def test_clean_text_blanks_and_curly_apostrophes():
    qlog = QualityLog()
    df = pd.DataFrame({"name": ["  Blakely’s  Red\nGum ", "   ", "Box"]})
    out = clean_text(df, "supply", qlog)
    assert out["name"].tolist()[0] == "Blakely's Red Gum"
    assert pd.isna(out["name"].tolist()[1])
    log = qlog.to_frame().set_index("check")["rows_affected"]
    assert log["Blank or whitespace-only cells"] == 1
    assert log["Curly apostrophes (’) in names"] == 1


def test_to_dates_handles_both_formats():
    qlog = QualityLog()
    df = pd.DataFrame({"d": ["June 28, 2023", "2023-06-29", "rubbish", None]})
    to_dates(df, "t", ["d"], qlog)
    assert df["d"].tolist()[:2] == [pd.Timestamp("2023-06-28"), pd.Timestamp("2023-06-29")]
    checks = qlog.to_frame().set_index("check")["rows_affected"]
    assert checks["Mixed date formats (some YYYY-MM-DD)"] == 1
    assert checks["Date could not be read"] == 1
