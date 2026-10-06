# STEP 1: Imports and file locations
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

transactions = pd.read_csv(PROCESSED / "transactions_clean.csv",
                           parse_dates=["transaction_date"])
gap = pd.read_csv(PROCESSED / "gap_ranking.csv")


# STEP 2: Keep sales with a real market price
# (transfers with a price above $0, excluding disclosed philanthropic transfers)
sales = transactions[
    transactions["price_valid"]
    & (transactions["philanthropic_reason_for_transfer_disclosed"] != "Yes")
].copy()
sales["year"] = sales["transaction_date"].dt.year
sales["sale_value"] = sales["price_per_credit_ex_gst"] * sales["number_of_credits"]


# STEP 3: Price per credit by year and credit class
# Median is used because a few very large or very expensive sales would distort an average
by_year = (sales.groupby(["year", "credit_class"])
           .agg(sales=("price_per_credit_ex_gst", "size"),
                credits_sold=("number_of_credits", "sum"),
                median_price=("price_per_credit_ex_gst", "median"),
                lower_quartile=("price_per_credit_ex_gst", lambda p: p.quantile(0.25)),
                upper_quartile=("price_per_credit_ex_gst", lambda p: p.quantile(0.75)),
                total_value=("sale_value", "sum"))
           .reset_index())
by_year["partial_year"] = by_year["year"] == sales["transaction_date"].max().year


# STEP 4: Median price for each credit type, joined to the scarcity ranking
by_type = (sales.groupby("credit_key")
           .agg(sales=("price_per_credit_ex_gst", "size"),
                median_price=("price_per_credit_ex_gst", "median"))
           .reset_index())
priced = gap.merge(by_type, on="credit_key", how="inner")


# STEP 5: Do scarcer credit types sell for more?
bands = pd.cut(priced["years_of_supply"], bins=[-0.01, 0, 1, 10, float("inf")],
               labels=["0 years (none left)", "Under 1 year", "1 to 10 years", "Over 10 years"])
priced["scarcity_band"] = bands
by_scarcity = (priced.groupby(["credit_class", "scarcity_band"], observed=True)
               .agg(credit_types=("credit_key", "size"),
                    median_price=("median_price", "median"))
               .reset_index())


# STEP 6: Save the results for Power BI
by_year.to_csv(PROCESSED / "price_by_year.csv", index=False)
priced.to_csv(PROCESSED / "price_by_credit_type.csv", index=False)
by_scarcity.to_csv(PROCESSED / "price_by_scarcity.csv", index=False)


# STEP 7: Print a summary
pd.set_option("display.width", 200)
print(f"Sales used for prices: {len(sales):,} "
      f"({sales['year'].min()}-{sales['year'].max()}; "
      f"{sales['year'].max()} is a partial year)")
print("\nMedian price per credit by year ($, ex GST):")
table = by_year.pivot(index="year", columns="credit_class", values="median_price")
print(table.round(0).to_string())
print("\nMedian price by scarcity ($, ex GST):")
print(by_scarcity.round(0).to_string(index=False))
print(f"\nSaved price_by_year.csv, price_by_credit_type.csv, price_by_scarcity.csv to {PROCESSED}")
