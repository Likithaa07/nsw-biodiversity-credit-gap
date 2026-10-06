# STEP 1: Imports and file locations
from pathlib import Path

import pandas as pd

from readers import read_xml_register, read_html_register

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
PROCESSED.mkdir(parents=True, exist_ok=True)


# STEP 2: A log that records every data quality issue and what we did about it
issues = []


def log(dataset, check, rows, action, column=""):
    issues.append({"dataset": dataset, "check": check, "column": column,
                   "rows_affected": int(rows), "action": action})


# STEP 3: Load the three registers
demand = read_xml_register(str(RAW / "Demand.xls"), "Credit status")
supply = read_xml_register(str(RAW / "Supply.xls"), "Credit ID")
transactions = read_html_register(str(RAW / "Transactions.xls"))

log("demand", "Register has no listings", 1 if len(demand) == 0 else 0,
    "Used credit retirements as the demand measure instead")


# STEP 4: Tidy column names (lowercase, underscores, no symbols)
def tidy_columns(df):
    df.columns = (df.columns.str.strip().str.lower()
                  .str.replace(r"[^a-z0-9]+", "_", regex=True).str.strip("_"))
    return df


supply = tidy_columns(supply)
transactions = tidy_columns(transactions)

# Use the same names in both tables so they can be matched later
transactions = transactions.rename(columns={
    "sub_region": "ibra_subregion",
    "plant_community_type": "plant_community_type_common_name",
    "scientific_name": "species_scientific_name",
    "common_name": "species_common_name",
})


# STEP 5: Remove personal contact details (privacy: not needed for the analysis)
personal = ["business_name", "business_phone", "business_email", "contact_first_name",
            "contact_last_name", "contact_email", "contact_phone", "contact_mobile",
            "lot_and_plan", "address_of_obligation"]
for name, df in [("supply", supply), ("transactions", transactions)]:
    cols = [c for c in personal if c in df.columns]
    df.drop(columns=cols, inplace=True)
    log(name, f"Personal contact columns ({len(cols)})", len(df), "Removed for privacy")


# STEP 6: Clean text - trim spaces/newlines, make blanks missing, fix curly apostrophes
def clean_text(df, name):
    text_cols = df.select_dtypes(include=["object", "string"]).columns
    blanks = 0
    curly = 0
    for c in text_cols:
        s = df[c].astype("string")
        s = s.str.replace(r"\s+", " ", regex=True).str.strip()
        curly += s.str.contains("’", na=False).sum()
        s = s.str.replace("’", "'", regex=False)
        blanks += (s == "").sum()
        df[c] = s.replace("", pd.NA)
    log(name, "Blank or whitespace-only cells", blanks, "Set to missing")
    log(name, "Curly apostrophes (’) in names", curly, "Replaced with straight apostrophe (')")
    return df


supply = clean_text(supply, "supply")
transactions = clean_text(transactions, "transactions")


# STEP 7: Convert numbers and dates to proper types
def to_dates(df, name, cols):
    for c in cols:
        present = df[c].notna()
        dates = pd.to_datetime(df[c], format="%B %d, %Y", errors="coerce")  # e.g. June 28, 2023
        iso = pd.to_datetime(df[c], format="%Y-%m-%d", errors="coerce")     # e.g. 2023-06-28
        if (dates.isna() & iso.notna()).sum():
            log(name, "Mixed date formats (some YYYY-MM-DD)", (dates.isna() & iso.notna()).sum(),
                "Converted to one date format", c)
        df[c] = dates.fillna(iso)
        if (present & df[c].isna()).sum():
            log(name, "Date could not be read", (present & df[c].isna()).sum(), "Set to missing", c)


supply["number_of_credits"] = pd.to_numeric(supply["number_of_credits"], errors="coerce")
supply["pct_id"] = pd.to_numeric(supply["pct_id"], errors="coerce").astype("Int64")
supply["site_area_ha"] = pd.to_numeric(supply["site_area_ha"], errors="coerce")
to_dates(supply, "supply", ["date_credits_issued", "listed_date", "public_register_expiry_date",
                            "suspension_start_date", "suspension_end_date",
                            "cancellation_start_date"])

transactions["number_of_credits"] = pd.to_numeric(transactions["number_of_credits"], errors="coerce")
transactions["price_per_credit_ex_gst"] = pd.to_numeric(transactions["price_per_credit_ex_gst"],
                                                        errors="coerce")
to_dates(transactions, "transactions", ["transaction_date", "date_of_consent_approval"])


# STEP 8: Supply quality checks
dup = supply["credit_id"].duplicated()
log("supply", "Duplicate Credit ID", dup.sum(), "Dropped duplicates", "credit_id")
supply = supply[~dup]

bad = supply["number_of_credits"].isna() | (supply["number_of_credits"] <= 0)
log("supply", "Number of credits missing, zero or negative (Expressions of Interest)",
    bad.sum(), "Dropped rows", "number_of_credits")
supply = supply[~bad]

eco = supply["ecosystem_or_species"] == "Ecosystem"
log("supply", "Ecosystem credit with no PCT ID", (eco & supply["pct_id"].isna()).sum(),
    "Kept, flagged (cannot be matched to demand)", "pct_id")
log("supply", "Species credit with no species name",
    (~eco & supply["species_scientific_name"].isna()).sum(),
    "Kept, flagged (cannot be matched to demand)", "species_scientific_name")
log("supply", "Missing IBRA subregion", supply["ibra_subregion"].isna().sum(),
    "Kept, flagged", "ibra_subregion")


# STEP 9: Transactions quality checks
empty = (transactions["transaction_date"].isna() & transactions["transaction_type"].isna()
         & transactions["number_of_credits"].isna())
log("transactions", "Row with no date, type or number of credits", empty.sum(), "Dropped rows")
transactions = transactions[~empty]

dup = transactions.duplicated()
log("transactions", "Exact duplicate rows", dup.sum(), "Dropped duplicates")
transactions = transactions[~dup]

repeat_ids = transactions["transaction_id"].duplicated(keep=False).sum()
log("transactions", "Transaction ID appears on several rows", repeat_ids,
    "Kept (one transaction can cover several credit types)", "transaction_id")

is_transfer = transactions["transaction_type"] == "Transfer"
no_price = is_transfer & (transactions["price_per_credit_ex_gst"].isna()
                          | (transactions["price_per_credit_ex_gst"] <= 0))
transactions["price_valid"] = is_transfer & ~no_price
log("transactions", "Transfer with missing or $0 price", no_price.sum(),
    "Kept, excluded from price analysis", "price_per_credit_ex_gst")

log("transactions", "Cancelled transactions", (transactions["transaction_type"] == "Cancelled").sum(),
    "Kept, excluded from demand", "transaction_type")


# STEP 10: Add a credit type key so supply and transactions can be matched
supply["credit_class"] = supply["ecosystem_or_species"]
transactions["credit_class"] = transactions["species_scientific_name"].notna().map(
    {True: "Species", False: "Ecosystem"})

# Transactions have no PCT ID, so look it up from the PCT name in the supply register
pct_lookup = (supply.dropna(subset=["pct_id", "plant_community_type_common_name"])
              .drop_duplicates("plant_community_type_common_name")
              .set_index("plant_community_type_common_name")["pct_id"])
transactions["pct_id"] = transactions["plant_community_type_common_name"].map(pct_lookup).astype("Int64")
unmatched = (transactions["credit_class"] == "Ecosystem") & transactions["pct_id"].isna()
log("transactions", "PCT name not found in supply register", unmatched.sum(),
    "Kept, flagged (no PCT ID)", "pct_id")


def credit_key(df):
    key = "PCT " + df["pct_id"].astype("string")
    return key.where(df["credit_class"] == "Ecosystem", df["species_scientific_name"])


supply["credit_key"] = credit_key(supply)
transactions["credit_key"] = credit_key(transactions)


# STEP 11: Save the clean data and the data quality log
supply.to_csv(PROCESSED / "supply_clean.csv", index=False)
transactions.to_csv(PROCESSED / "transactions_clean.csv", index=False)
quality_log = pd.DataFrame(issues)
quality_log.to_csv(PROCESSED / "data_quality_log.csv", index=False)

print(f"Supply clean:       {len(supply):,} rows")
print(f"Transactions clean: {len(transactions):,} rows")
print("\nData quality log:")
pd.set_option("display.width", 200)
pd.set_option("display.max_colwidth", 60)
print(quality_log[["dataset", "check", "rows_affected", "action"]].to_string(index=False))
print(f"\nSaved to {PROCESSED}")
