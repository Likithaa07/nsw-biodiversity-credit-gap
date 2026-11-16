"""Clean the three BOS registers, log every data quality issue, and save analysis-ready files."""
# STEP 1: Imports and file locations
from __future__ import annotations

from pathlib import Path

import pandas as pd

from common import (PROCESSED, RAW, DataValidationError, get_logger, require_columns,
                    require_files, require_in_range, require_min_rows, require_share_not_null,
                    require_unique)
from readers import read_html_register, read_xml_register

log = get_logger("clean")

RAW_FILES = {"demand": "Demand.xls", "supply": "Supply.xls", "transactions": "Transactions.xls"}
SUPPLY_COLUMNS = ["credit_id", "credit_status", "ecosystem_or_species", "number_of_credits",
                  "pct_id", "plant_community_type_common_name", "species_scientific_name",
                  "ibra_subregion"]
TRANSACTION_COLUMNS = ["transaction_date", "transaction_id", "transaction_type",
                       "number_of_credits", "price_per_credit_ex_gst",
                       "plant_community_type_common_name", "species_scientific_name"]
PERSONAL = ["business_name", "business_phone", "business_email", "contact_first_name",
            "contact_last_name", "contact_email", "contact_phone", "contact_mobile",
            "lot_and_plan", "address_of_obligation"]


# STEP 2: A log that records every data quality issue and what we did about it
class QualityLog:
    """Collects one row per data quality check."""

    def __init__(self) -> None:
        self.issues: list[dict] = []

    def add(self, dataset: str, check: str, rows: int, action: str, column: str = "") -> None:
        self.issues.append({"dataset": dataset, "check": check, "column": column,
                            "rows_affected": int(rows), "action": action})

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.issues)


# STEP 3: Load the three registers
def load_registers(raw_dir: Path = RAW) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    paths = {k: Path(raw_dir) / v for k, v in RAW_FILES.items()}
    require_files(*paths.values(),
                  hint="Download the registers first: see data/raw/README.md or the refresh guide.")
    demand = read_xml_register(paths["demand"], "Credit status")
    supply = read_xml_register(paths["supply"], "Credit ID")
    transactions = read_html_register(paths["transactions"])
    log.info("Loaded demand %s, supply %s, transactions %s",
             demand.shape, supply.shape, transactions.shape)
    return demand, supply, transactions


# STEP 4: Tidy column names (lowercase, underscores, no symbols)
def tidy_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = (df.columns.str.strip().str.lower()
                  .str.replace(r"[^a-z0-9]+", "_", regex=True).str.strip("_"))
    return df


def harmonise_transaction_columns(transactions: pd.DataFrame) -> pd.DataFrame:
    """Use the same names in both tables so they can be matched later."""
    return transactions.rename(columns={
        "sub_region": "ibra_subregion",
        "plant_community_type": "plant_community_type_common_name",
        "scientific_name": "species_scientific_name",
        "common_name": "species_common_name",
    })


# STEP 5: Remove personal contact details (privacy: not needed for the analysis)
def drop_personal(df: pd.DataFrame, name: str, qlog: QualityLog) -> None:
    cols = [c for c in PERSONAL if c in df.columns]
    df.drop(columns=cols, inplace=True)
    qlog.add(name, f"Personal contact columns ({len(cols)})", len(df), "Removed for privacy")


# STEP 6: Clean text - trim spaces/newlines, make blanks missing, fix curly apostrophes
def clean_text(df: pd.DataFrame, name: str, qlog: QualityLog) -> pd.DataFrame:
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
    qlog.add(name, "Blank or whitespace-only cells", blanks, "Set to missing")
    qlog.add(name, "Curly apostrophes (’) in names", curly, "Replaced with straight apostrophe (')")
    return df


# STEP 7: Convert numbers and dates to proper types
def to_dates(df: pd.DataFrame, name: str, cols: list[str], qlog: QualityLog) -> None:
    for c in cols:
        present = df[c].notna()
        dates = pd.to_datetime(df[c], format="%B %d, %Y", errors="coerce")  # e.g. June 28, 2023
        iso = pd.to_datetime(df[c], format="%Y-%m-%d", errors="coerce")     # e.g. 2023-06-28
        if (dates.isna() & iso.notna()).sum():
            qlog.add(name, "Mixed date formats (some YYYY-MM-DD)",
                     (dates.isna() & iso.notna()).sum(), "Converted to one date format", c)
        df[c] = dates.fillna(iso)
        if (present & df[c].isna()).sum():
            qlog.add(name, "Date could not be read", (present & df[c].isna()).sum(),
                     "Set to missing", c)


def convert_types(supply: pd.DataFrame, transactions: pd.DataFrame, qlog: QualityLog) -> None:
    supply["number_of_credits"] = pd.to_numeric(supply["number_of_credits"], errors="coerce")
    supply["pct_id"] = pd.to_numeric(supply["pct_id"], errors="coerce").astype("Int64")
    supply["site_area_ha"] = pd.to_numeric(supply["site_area_ha"], errors="coerce")
    to_dates(supply, "supply", ["date_credits_issued", "listed_date", "public_register_expiry_date",
                                "suspension_start_date", "suspension_end_date",
                                "cancellation_start_date"], qlog)

    transactions["number_of_credits"] = pd.to_numeric(transactions["number_of_credits"],
                                                      errors="coerce")
    transactions["price_per_credit_ex_gst"] = pd.to_numeric(
        transactions["price_per_credit_ex_gst"], errors="coerce")
    to_dates(transactions, "transactions", ["transaction_date", "date_of_consent_approval"], qlog)


# STEP 8: Supply quality checks
def check_supply(supply: pd.DataFrame, qlog: QualityLog) -> pd.DataFrame:
    dup = supply["credit_id"].duplicated()
    qlog.add("supply", "Duplicate Credit ID", dup.sum(), "Dropped duplicates", "credit_id")
    supply = supply[~dup]

    bad = supply["number_of_credits"].isna() | (supply["number_of_credits"] <= 0)
    qlog.add("supply", "Number of credits missing, zero or negative (Expressions of Interest)",
             bad.sum(), "Dropped rows", "number_of_credits")
    supply = supply[~bad]

    eco = supply["ecosystem_or_species"] == "Ecosystem"
    qlog.add("supply", "Ecosystem credit with no PCT ID", (eco & supply["pct_id"].isna()).sum(),
             "Kept, flagged (cannot be matched to demand)", "pct_id")
    qlog.add("supply", "Species credit with no species name",
             (~eco & supply["species_scientific_name"].isna()).sum(),
             "Kept, flagged (cannot be matched to demand)", "species_scientific_name")
    qlog.add("supply", "Missing IBRA subregion (BioBanking equivalence species credits)",
             supply["ibra_subregion"].isna().sum(),
             "Kept; expected, species credits are matched by species not region", "ibra_subregion")
    return supply


# STEP 9: Transactions quality checks
def check_transactions(transactions: pd.DataFrame, qlog: QualityLog) -> pd.DataFrame:
    empty = (transactions["transaction_date"].isna() & transactions["transaction_type"].isna()
             & transactions["number_of_credits"].isna())
    qlog.add("transactions", "Row with no date, type or number of credits", empty.sum(),
             "Dropped rows")
    transactions = transactions[~empty]

    dup = transactions.duplicated()
    qlog.add("transactions", "Exact duplicate rows", dup.sum(), "Dropped duplicates")
    transactions = transactions[~dup]

    repeat_ids = transactions["transaction_id"].duplicated(keep=False).sum()
    qlog.add("transactions", "Transaction ID appears on several rows", repeat_ids,
             "Kept (one transaction can cover several credit types)", "transaction_id")

    is_transfer = transactions["transaction_type"] == "Transfer"
    no_price = is_transfer & (transactions["price_per_credit_ex_gst"].isna()
                              | (transactions["price_per_credit_ex_gst"] <= 0))
    transactions["price_valid"] = is_transfer & ~no_price
    qlog.add("transactions", "Transfer with missing or $0 price", no_price.sum(),
             "Kept, excluded from price analysis", "price_per_credit_ex_gst")

    qlog.add("transactions", "Cancelled transactions",
             (transactions["transaction_type"] == "Cancelled").sum(),
             "Kept, excluded from demand", "transaction_type")
    return transactions


# STEP 10: Add a credit type key so supply and transactions can be matched
def simplify(names: pd.Series) -> pd.Series:
    """The registers spell some PCT names differently (e.g. "Blakelys" vs "Blakely's"),
    so match on a simplified name: lowercase, no apostrophes, no punctuation."""
    return (names.str.lower().str.replace("'", "", regex=False)
            .str.replace(r"[^a-z0-9]+", " ", regex=True).str.strip())


def add_credit_keys(supply: pd.DataFrame, transactions: pd.DataFrame, qlog: QualityLog) -> None:
    supply["credit_class"] = supply["ecosystem_or_species"]
    transactions["credit_class"] = transactions["species_scientific_name"].notna().map(
        {True: "Species", False: "Ecosystem"})

    supply["pct_name_key"] = simplify(supply["plant_community_type_common_name"])
    transactions["pct_name_key"] = simplify(transactions["plant_community_type_common_name"])

    # Transactions have no PCT ID, so look it up from supply using the simplified name
    pct_lookup = (supply.dropna(subset=["pct_id", "pct_name_key"])
                  .drop_duplicates("pct_name_key")
                  .set_index("pct_name_key")["pct_id"])
    transactions["pct_id"] = transactions["pct_name_key"].map(pct_lookup).astype("Int64")

    eco_tx = transactions["credit_class"] == "Ecosystem"
    exact = transactions["plant_community_type_common_name"].isin(
        supply["plant_community_type_common_name"])
    qlog.add("transactions", "PCT name spelt differently from supply register",
             (eco_tx & ~exact & transactions["pct_id"].notna()).sum(),
             "Fixed by matching on simplified name", "plant_community_type_common_name")
    qlog.add("transactions", "PCT has no credits left in the supply register",
             (eco_tx & transactions["pct_id"].isna()).sum(),
             "Kept; counted as zero supply in the gap analysis", "pct_id")

    # Credit key: simplified PCT name for ecosystem credits, scientific name for species credits
    supply["credit_key"] = supply["pct_name_key"].where(
        supply["credit_class"] == "Ecosystem", supply["species_scientific_name"])
    transactions["credit_key"] = transactions["pct_name_key"].where(
        eco_tx, transactions["species_scientific_name"])


# STEP 11: Final validation - stop the pipeline if the clean data looks wrong
def validate_clean(supply: pd.DataFrame, transactions: pd.DataFrame) -> None:
    require_min_rows(supply, 100, "supply_clean")
    require_min_rows(transactions, 100, "transactions_clean")
    require_unique(supply, "credit_id", "supply_clean")
    require_in_range(supply["number_of_credits"], "supply credits", low=0.0001)
    require_in_range(transactions["number_of_credits"], "transaction credits", low=0)
    require_in_range(transactions["price_per_credit_ex_gst"], "price per credit", low=0)
    today = pd.Timestamp.today()
    require_in_range(transactions["transaction_date"], "transaction dates",
                     low=pd.Timestamp("2017-01-01"), high=today + pd.Timedelta(days=1))
    retire = transactions[transactions["transaction_type"] == "Retire"]
    require_share_not_null(retire["credit_key"], "retirement credit keys", 0.95)
    if not set(transactions["transaction_type"].dropna()) & {"Retire", "Transfer"}:
        raise DataValidationError("transactions_clean: no 'Retire' or 'Transfer' rows found.")
    log.info("Validation passed: %s supply rows, %s transaction rows",
             f"{len(supply):,}", f"{len(transactions):,}")


# STEP 12: Run every step and save the clean data and the data quality log
def main(raw_dir: Path = RAW, processed_dir: Path = PROCESSED) -> pd.DataFrame:
    processed_dir = Path(processed_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    qlog = QualityLog()

    demand, supply, transactions = load_registers(raw_dir)
    qlog.add("demand", "Register has no listings", 1 if len(demand) == 0 else 0,
             "Used credit retirements as the demand measure instead")

    supply = tidy_columns(supply)
    transactions = harmonise_transaction_columns(tidy_columns(transactions))
    require_columns(supply, SUPPLY_COLUMNS, "Supply register")
    require_columns(transactions, TRANSACTION_COLUMNS, "Transactions register")

    for name, df in [("supply", supply), ("transactions", transactions)]:
        drop_personal(df, name, qlog)
    supply = clean_text(supply, "supply", qlog)
    transactions = clean_text(transactions, "transactions", qlog)
    convert_types(supply, transactions, qlog)
    supply = check_supply(supply, qlog)
    transactions = check_transactions(transactions, qlog)
    add_credit_keys(supply, transactions, qlog)
    validate_clean(supply, transactions)

    supply.to_csv(processed_dir / "supply_clean.csv", index=False)
    transactions.to_csv(processed_dir / "transactions_clean.csv", index=False)
    quality_log = qlog.to_frame()
    quality_log.to_csv(processed_dir / "data_quality_log.csv", index=False)

    log.info("Supply clean: %s rows; transactions clean: %s rows",
             f"{len(supply):,}", f"{len(transactions):,}")
    log.info("Data quality log:\n%s",
             quality_log[["dataset", "check", "rows_affected", "action"]].to_string(index=False))
    log.info("Saved to %s", processed_dir)
    return quality_log


if __name__ == "__main__":
    main()
