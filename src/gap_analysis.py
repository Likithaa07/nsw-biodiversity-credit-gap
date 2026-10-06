# STEP 1: Imports and file locations
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

supply = pd.read_csv(PROCESSED / "supply_clean.csv")
transactions = pd.read_csv(PROCESSED / "transactions_clean.csv",
                           parse_dates=["transaction_date"])


# STEP 2: Supply - credits available now, and credits in the pipeline
available = supply["credit_status"].isin(["Issued", "Equivalence Credit"])
pending = supply["credit_status"] == "Pending Review"

supply_by_type = pd.DataFrame({
    "available_credits": supply[available].groupby("credit_key")["number_of_credits"].sum(),
    "pending_credits": supply[pending].groupby("credit_key")["number_of_credits"].sum(),
})


# STEP 3: Demand - credits retired per year (retirements meet real offset obligations)
retired = transactions[transactions["transaction_type"] == "Retire"]
years_of_data = (transactions["transaction_date"].max()
                 - transactions["transaction_date"].min()).days / 365.25

demand_by_type = pd.DataFrame({
    "retired_credits": retired.groupby("credit_key")["number_of_credits"].sum(),
    "retirement_count": retired.groupby("credit_key").size(),
})
demand_by_type["retired_per_year"] = demand_by_type["retired_credits"] / years_of_data


# STEP 4: Readable labels for each credit type
labels = pd.concat([
    supply[["credit_key", "credit_class", "plant_community_type_common_name",
            "species_common_name", "species_scientific_name", "offset_trading_group"]],
    transactions[["credit_key", "credit_class", "plant_community_type_common_name",
                  "species_common_name", "species_scientific_name", "offset_trading_group"]],
]).drop_duplicates("credit_key").set_index("credit_key")

species_label = (labels["species_common_name"].fillna(labels["species_scientific_name"])
                 + " (" + labels["species_scientific_name"] + ")")
labels["credit_name"] = labels["plant_community_type_common_name"].where(
    labels["credit_class"] == "Ecosystem", species_label)


# STEP 5: Combine supply and demand, and calculate years of supply left
gap = supply_by_type.join(demand_by_type, how="outer").fillna(0)
gap = labels[["credit_class", "credit_name", "offset_trading_group"]].join(gap, how="right")

gap["gap_credits"] = gap["retired_per_year"] - gap["available_credits"]
gap["years_of_supply"] = (gap["available_credits"] / gap["retired_per_year"]).where(
    gap["retired_per_year"] > 0)
gap["zero_supply"] = gap["available_credits"] == 0


# STEP 6: Rank - only credit types that have been in demand; fewest years left = most scarce
ranked = (gap[gap["retired_per_year"] > 0]
          .sort_values(["years_of_supply", "retired_per_year"], ascending=[True, False])
          .reset_index())
ranked.insert(0, "scarcity_rank", range(1, len(ranked) + 1))

ranked.to_csv(PROCESSED / "gap_ranking.csv", index=False)


# STEP 7: Print a summary
print(f"Demand period: {years_of_data:.1f} years of transactions")
print(f"Credit types in demand: {len(ranked)}")
print(f"  with zero credits available: {ranked['zero_supply'].sum()}")
print(f"  with less than 1 year of supply: {(ranked['years_of_supply'] < 1).sum()}")
print("\nTop 10 most under-supplied credit types:")
pd.set_option("display.width", 200)
top = ranked.head(10)[["scarcity_rank", "credit_class", "credit_name",
                       "available_credits", "retired_per_year", "years_of_supply"]].copy()
top["credit_name"] = top["credit_name"].str[:60]  # shorten long names for printing only
print(top.round(1).to_string(index=False))
print(f"\nSaved to {PROCESSED / 'gap_ranking.csv'}")
