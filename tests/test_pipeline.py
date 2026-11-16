"""End-to-end test: run the real pipeline on the committed registers and check the headline
findings in the README still hold. Writes to a temporary folder, so nothing is overwritten."""
# STEP 1: Imports
import pandas as pd
import pytest

import clean
import gap_analysis
import price_model
import price_trends
from common import RAW

pytestmark = pytest.mark.skipif(not (RAW / "Supply.xls").exists(), reason="raw data not present")


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    out = tmp_path_factory.mktemp("processed")
    quality = clean.main(processed_dir=out)
    ranked = gap_analysis.main(processed_dir=out)
    by_scarcity = price_trends.main(processed_dir=out)
    return {"quality": quality, "ranked": ranked, "by_scarcity": by_scarcity, "dir": out}


# STEP 2: Headline numbers from the README
def test_headline_findings(results):
    ranked = results["ranked"]
    assert len(ranked) == 305
    assert ranked["zero_supply"].sum() == 43
    assert (ranked["years_of_supply"] < 1).sum() == 71
    assert ranked.iloc[0]["credit_name"].startswith("Black Cypress Pine")
    assert ranked.iloc[0]["retired_per_year"] == pytest.approx(507, abs=1)


def test_quality_log_counts(results):
    log = results["quality"].set_index(["dataset", "check"])["rows_affected"]
    assert log[("transactions", "PCT name spelt differently from supply register")] == 95
    assert log[("transactions", "PCT has no credits left in the supply register")] == 127


def test_clean_files_have_no_personal_details(results):
    supply = pd.read_csv(results["dir"] / "supply_clean.csv", nrows=5)
    assert not {"contact_email", "contact_phone", "business_email"} & set(supply.columns)


def test_scarce_ecosystem_credits_cost_more(results):
    eco = results["by_scarcity"].query("credit_class == 'Ecosystem'").set_index("scarcity_band")
    assert eco.loc["0 years (none left)", "median_price"] > eco.loc["Over 10 years", "median_price"]


def test_price_model_finds_scarcity_premium(results, tmp_path):
    out = price_model.main(processed_dir=results["dir"], figures_dir=tmp_path)
    coefs = out["coefs"].set_index("term")
    assert coefs.loc["None left", "effect_pct"] > 0
    assert coefs.loc["None left", "p_value"] < 0.01
    scores = out["scores"].set_index(["model", "test"])["r2_log_price"]
    cv = "5-fold, unseen credit types"
    assert scores[("Gradient boosting", cv)] > scores[("Baseline", cv)]
