"""Compare credit supply with demand (retirements) and rank credit types by scarcity."""
# STEP 1: Imports and file locations
from __future__ import annotations

from pathlib import Path

import pandas as pd

from common import PROCESSED, get_logger, require_columns, require_files, require_min_rows

log = get_logger("gap_analysis")

AVAILABLE_STATUSES = ["Issued", "Equivalence Credit"]
PENDING_STATUS = "Pending Review"
MIN_REGION_DEMAND = 50  # ignore subregions with fewer credits retired a year than this
LABEL_COLUMNS = ["credit_key", "credit_class", "plant_community_type_common_name",
                 "species_common_name", "species_scientific_name", "offset_trading_group"]


# STEP 2: Load the clean data made by clean.py
def load_clean(processed_dir: Path = PROCESSED) -> tuple[pd.DataFrame, pd.DataFrame]:
    supply_path = Path(processed_dir) / "supply_clean.csv"
    tx_path = Path(processed_dir) / "transactions_clean.csv"
    require_files(supply_path, tx_path, hint="Run clean.py first.")
    supply = pd.read_csv(supply_path)
    transactions = pd.read_csv(tx_path, parse_dates=["transaction_date"])
    require_columns(supply, ["credit_key", "credit_status", "number_of_credits",
                             "ibra_subregion", "ibra_region"] + LABEL_COLUMNS, "supply_clean")
    require_columns(transactions, ["transaction_date", "transaction_type", "number_of_credits",
                                   "ibra_subregion"] + LABEL_COLUMNS, "transactions_clean")
    require_min_rows(supply, 1, "supply_clean")
    require_min_rows(transactions, 1, "transactions_clean")
    return supply, transactions


# STEP 3: How many years of transactions there are (used to turn totals into yearly rates)
def years_of_data(transactions: pd.DataFrame) -> float:
    dates = transactions["transaction_date"]
    return (dates.max() - dates.min()).days / 365.25


# STEP 4: Rank every credit type that has been in demand; fewest years left = most scarce
def rank_credit_types(supply: pd.DataFrame, transactions: pd.DataFrame) -> pd.DataFrame:
    available = supply["credit_status"].isin(AVAILABLE_STATUSES)
    pending = supply["credit_status"] == PENDING_STATUS
    supply_by_type = pd.DataFrame({
        "available_credits": supply[available].groupby("credit_key")["number_of_credits"].sum(),
        "pending_credits": supply[pending].groupby("credit_key")["number_of_credits"].sum(),
    })

    # Demand = credits retired per year (retirements meet real offset obligations)
    retired = transactions[transactions["transaction_type"] == "Retire"]
    demand_by_type = pd.DataFrame({
        "retired_credits": retired.groupby("credit_key")["number_of_credits"].sum(),
        "retirement_count": retired.groupby("credit_key").size(),
    })
    demand_by_type["retired_per_year"] = (demand_by_type["retired_credits"]
                                          / years_of_data(transactions))

    # Readable labels for each credit type
    labels = (pd.concat([supply[LABEL_COLUMNS], transactions[LABEL_COLUMNS]])
              .drop_duplicates("credit_key").set_index("credit_key"))
    species_label = (labels["species_common_name"].fillna(labels["species_scientific_name"])
                     + " (" + labels["species_scientific_name"] + ")")
    labels["credit_name"] = labels["plant_community_type_common_name"].where(
        labels["credit_class"] == "Ecosystem", species_label)

    # Combine supply and demand, and calculate years of supply left
    gap = supply_by_type.join(demand_by_type, how="outer").fillna(0)
    gap = labels[["credit_class", "credit_name", "offset_trading_group"]].join(gap, how="right")
    gap["gap_credits"] = gap["retired_per_year"] - gap["available_credits"]
    gap["years_of_supply"] = (gap["available_credits"] / gap["retired_per_year"]).where(
        gap["retired_per_year"] > 0)
    gap["zero_supply"] = gap["available_credits"] == 0

    ranked = (gap[gap["retired_per_year"] > 0]
              .sort_values(["years_of_supply", "retired_per_year"], ascending=[True, False])
              .reset_index())
    ranked.insert(0, "scarcity_rank", range(1, len(ranked) + 1))
    return ranked


# STEP 5: Gap by region - all credits in each IBRA subregion pooled together
# (a broad view of where pressure is highest; real like-for-like matching is narrower)
def gap_by_region(supply: pd.DataFrame, transactions: pd.DataFrame,
                  min_demand: float = MIN_REGION_DEMAND) -> pd.DataFrame:
    available = supply["credit_status"].isin(AVAILABLE_STATUSES)
    pending = supply["credit_status"] == PENDING_STATUS
    retired = transactions[transactions["transaction_type"] == "Retire"]

    region_names = (supply.dropna(subset=["ibra_subregion", "ibra_region"])
                    .drop_duplicates("ibra_subregion").set_index("ibra_subregion")["ibra_region"])
    region = pd.DataFrame({
        "available_credits": supply[available].groupby("ibra_subregion")["number_of_credits"].sum(),
        "pending_credits": supply[pending].groupby("ibra_subregion")["number_of_credits"].sum(),
        "retired_per_year": (retired.groupby("ibra_subregion")["number_of_credits"].sum()
                             / years_of_data(transactions)),
    }).fillna(0)
    # Subregions with no supply listed have no region name in the data, so fill the known ones
    region_names = pd.concat([region_names,
                              pd.Series({"Pooncarie-Darling": "Murray Darling Depression"})])
    region["ibra_region"] = region.index.map(region_names)
    region["years_of_supply"] = (region["available_credits"] / region["retired_per_year"]).where(
        region["retired_per_year"] > 0)
    return (region[region["retired_per_year"] >= min_demand]
            .sort_values("years_of_supply").reset_index(names="ibra_subregion"))


# STEP 6: Run, save and log a summary
def main(processed_dir: Path = PROCESSED) -> pd.DataFrame:
    supply, transactions = load_clean(processed_dir)
    ranked = rank_credit_types(supply, transactions)
    region = gap_by_region(supply, transactions)
    ranked.to_csv(Path(processed_dir) / "gap_ranking.csv", index=False)
    region.to_csv(Path(processed_dir) / "gap_by_region.csv", index=False)

    pd.set_option("display.width", 200)
    top = ranked.head(10)[["scarcity_rank", "credit_class", "credit_name",
                           "available_credits", "retired_per_year", "years_of_supply"]].copy()
    top["credit_name"] = top["credit_name"].str[:60]  # shorten long names for the log only
    log.info("Demand period: %.1f years of transactions", years_of_data(transactions))
    log.info("Credit types in demand: %d (zero available: %d; under 1 year of supply: %d)",
             len(ranked), ranked["zero_supply"].sum(), (ranked["years_of_supply"] < 1).sum())
    log.info("Top 10 most under-supplied credit types:\n%s", top.round(1).to_string(index=False))
    log.info("Subregions with at least %d credits retired a year: %d\n%s", MIN_REGION_DEMAND,
             len(region),
             region.head(5)[["ibra_subregion", "ibra_region", "available_credits",
                             "retired_per_year", "years_of_supply"]].round(1).to_string(index=False))
    log.info("Saved gap_ranking.csv and gap_by_region.csv to %s", processed_dir)
    return ranked


if __name__ == "__main__":
    main()
