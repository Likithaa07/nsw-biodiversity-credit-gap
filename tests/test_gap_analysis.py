"""Tests for the scarcity ranking, on a tiny made-up market."""
# STEP 1: Imports
import pandas as pd
import pytest

from gap_analysis import rank_credit_types, years_of_data


def make_market():
    """Two credit types: 'a' has none left, 'b' has 10 available. 2 years of data."""
    common = {"credit_class": "Ecosystem", "species_common_name": None,
              "species_scientific_name": None, "offset_trading_group": "G"}
    supply = pd.DataFrame([
        {"credit_key": "b", "credit_status": "Issued", "number_of_credits": 10,
         "plant_community_type_common_name": "B forest", **common},
        {"credit_key": "b", "credit_status": "Pending Review", "number_of_credits": 4,
         "plant_community_type_common_name": "B forest", **common},
    ])
    transactions = pd.DataFrame([
        {"credit_key": "a", "transaction_type": "Retire", "number_of_credits": 8,
         "transaction_date": pd.Timestamp("2020-01-01"),
         "plant_community_type_common_name": "A woodland", **common},
        {"credit_key": "b", "transaction_type": "Retire", "number_of_credits": 10,
         "transaction_date": pd.Timestamp("2021-12-31"),
         "plant_community_type_common_name": "B forest", **common},
        {"credit_key": "b", "transaction_type": "Transfer", "number_of_credits": 99,
         "transaction_date": pd.Timestamp("2021-06-01"),
         "plant_community_type_common_name": "B forest", **common},
    ])
    return supply, transactions


# STEP 2: The ranking
def test_years_of_data():
    _, tx = make_market()
    assert years_of_data(tx) == pytest.approx(2.0, abs=0.01)


def test_zero_supply_ranks_first_and_transfers_are_not_demand():
    ranked = rank_credit_types(*make_market()).set_index("credit_key")
    assert ranked.loc["a", "scarcity_rank"] == 1
    assert ranked.loc["a", "zero_supply"]
    assert ranked.loc["a", "years_of_supply"] == 0
    # 'b': 10 available, 10 retired over ~2 years = ~5 a year, so ~2 years of supply
    assert ranked.loc["b", "retired_per_year"] == pytest.approx(5, rel=0.01)
    assert ranked.loc["b", "years_of_supply"] == pytest.approx(2, rel=0.01)
    assert ranked.loc["b", "pending_credits"] == 4
