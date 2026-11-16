"""Median credit prices by year, by credit type and by scarcity band."""
# STEP 1: Imports and file locations
from __future__ import annotations

from pathlib import Path

import pandas as pd

from common import PROCESSED, get_logger, require_columns, require_files

log = get_logger("price_trends")

SCARCITY_BINS = [-0.01, 0, 1, 10, float("inf")]
SCARCITY_LABELS = ["0 years (none left)", "Under 1 year", "1 to 10 years", "Over 10 years"]


# STEP 2: Load the clean transactions and the scarcity ranking
def load_inputs(processed_dir: Path = PROCESSED) -> tuple[pd.DataFrame, pd.DataFrame]:
    tx_path = Path(processed_dir) / "transactions_clean.csv"
    gap_path = Path(processed_dir) / "gap_ranking.csv"
    require_files(tx_path, gap_path, hint="Run clean.py and gap_analysis.py first.")
    transactions = pd.read_csv(tx_path, parse_dates=["transaction_date"])
    gap = pd.read_csv(gap_path)
    require_columns(transactions, ["price_valid", "philanthropic_reason_for_transfer_disclosed",
                                   "price_per_credit_ex_gst", "number_of_credits", "credit_key",
                                   "credit_class"], "transactions_clean")
    require_columns(gap, ["credit_key", "credit_class", "years_of_supply"], "gap_ranking")
    return transactions, gap


# STEP 3: Keep sales with a real market price
# (transfers with a price above $0, excluding disclosed philanthropic transfers)
def market_sales(transactions: pd.DataFrame) -> pd.DataFrame:
    sales = transactions[
        transactions["price_valid"]
        & (transactions["philanthropic_reason_for_transfer_disclosed"] != "Yes")
    ].copy()
    sales["year"] = sales["transaction_date"].dt.year
    sales["sale_value"] = sales["price_per_credit_ex_gst"] * sales["number_of_credits"]
    return sales


# STEP 4: Price per credit by year and credit class
# Median is used because a few very large or very expensive sales would distort an average
def price_by_year(sales: pd.DataFrame) -> pd.DataFrame:
    by_year = (sales.groupby(["year", "credit_class"])
               .agg(sales=("price_per_credit_ex_gst", "size"),
                    credits_sold=("number_of_credits", "sum"),
                    median_price=("price_per_credit_ex_gst", "median"),
                    lower_quartile=("price_per_credit_ex_gst", lambda p: p.quantile(0.25)),
                    upper_quartile=("price_per_credit_ex_gst", lambda p: p.quantile(0.75)),
                    total_value=("sale_value", "sum"))
               .reset_index())
    by_year["partial_year"] = by_year["year"] == sales["transaction_date"].max().year
    return by_year


# STEP 5: Median price for each credit type, joined to the scarcity ranking
def price_by_credit_type(sales: pd.DataFrame, gap: pd.DataFrame) -> pd.DataFrame:
    by_type = (sales.groupby("credit_key")
               .agg(sales=("price_per_credit_ex_gst", "size"),
                    median_price=("price_per_credit_ex_gst", "median"))
               .reset_index())
    priced = gap.merge(by_type, on="credit_key", how="inner")
    priced["scarcity_band"] = pd.cut(priced["years_of_supply"], bins=SCARCITY_BINS,
                                     labels=SCARCITY_LABELS)
    return priced


# STEP 6: Do scarcer credit types sell for more?
def price_by_scarcity(priced: pd.DataFrame) -> pd.DataFrame:
    return (priced.groupby(["credit_class", "scarcity_band"], observed=True)
            .agg(credit_types=("credit_key", "size"),
                 median_price=("median_price", "median"))
            .reset_index())


# STEP 7: Run, save the results for Power BI and log a summary
def main(processed_dir: Path = PROCESSED) -> pd.DataFrame:
    transactions, gap = load_inputs(processed_dir)
    sales = market_sales(transactions)
    by_year = price_by_year(sales)
    priced = price_by_credit_type(sales, gap)
    by_scarcity = price_by_scarcity(priced)

    by_year.to_csv(Path(processed_dir) / "price_by_year.csv", index=False)
    priced.to_csv(Path(processed_dir) / "price_by_credit_type.csv", index=False)
    by_scarcity.to_csv(Path(processed_dir) / "price_by_scarcity.csv", index=False)

    pd.set_option("display.width", 200)
    table = by_year.pivot(index="year", columns="credit_class", values="median_price")
    log.info("Sales used for prices: %s (%d-%d; %d is a partial year)", f"{len(sales):,}",
             sales["year"].min(), sales["year"].max(), sales["year"].max())
    log.info("Median price per credit by year ($, ex GST):\n%s", table.round(0).to_string())
    log.info("Median price by scarcity ($, ex GST):\n%s",
             by_scarcity.round(0).to_string(index=False))
    log.info("Saved price_by_year.csv, price_by_credit_type.csv, price_by_scarcity.csv to %s",
             processed_dir)
    return by_scarcity


if __name__ == "__main__":
    main()
