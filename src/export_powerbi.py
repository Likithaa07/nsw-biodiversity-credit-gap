"""Package the results as formatted Excel tables for the Power BI dashboard."""
# STEP 1: Imports and file locations
from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from common import OUTPUTS, PROCESSED, get_logger, require_files

log = get_logger("export_powerbi")

INPUTS = ["gap_ranking.csv", "price_by_year.csv", "price_by_scarcity.csv",
          "data_quality_log.csv", "supply_clean.csv", "transactions_clean.csv"]


# STEP 2: Market overview tables
def supply_summary(supply: pd.DataFrame) -> pd.DataFrame:
    summary = (supply.groupby(["credit_status", "credit_class", "ibra_region"], dropna=False)
               ["number_of_credits"].sum().reset_index()
               .rename(columns={"number_of_credits": "credits"}))
    summary["ibra_region"] = summary["ibra_region"].fillna("Not recorded")
    return summary


def activity_by_year(transactions: pd.DataFrame) -> pd.DataFrame:
    activity = transactions[transactions["transaction_type"].isin(["Transfer", "Retire"])].copy()
    activity["year"] = activity["transaction_date"].dt.year
    return (activity.groupby(["year", "transaction_type", "credit_class"])
            ["number_of_credits"].sum().reset_index()
            .rename(columns={"number_of_credits": "credits"}))


# STEP 3: Write every table to its own sheet, formatted as an Excel table
# (Power BI in the browser looks for tables)
def write_workbook(sheets: dict[str, pd.DataFrame], path: Path) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)
    wb = load_workbook(path)
    for name, df in sheets.items():
        ref = f"A1:{get_column_letter(df.shape[1])}{df.shape[0] + 1}"
        table = Table(displayName=name, ref=ref)
        table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        wb[name].add_table(table)
    wb.save(path)


# STEP 4: Run
def main(processed_dir: Path = PROCESSED, outputs_dir: Path = OUTPUTS) -> Path:
    processed_dir, outputs_dir = Path(processed_dir), Path(outputs_dir)
    require_files(*[processed_dir / f for f in INPUTS], hint="Run the earlier scripts first.")
    outputs_dir.mkdir(parents=True, exist_ok=True)
    transactions = pd.read_csv(processed_dir / "transactions_clean.csv",
                               parse_dates=["transaction_date"])
    sheets = {
        "gap_ranking": pd.read_csv(processed_dir / "gap_ranking.csv"),
        "price_by_year": pd.read_csv(processed_dir / "price_by_year.csv"),
        "price_by_scarcity": pd.read_csv(processed_dir / "price_by_scarcity.csv"),
        "supply_summary": supply_summary(pd.read_csv(processed_dir / "supply_clean.csv")),
        "activity_by_year": activity_by_year(transactions),
        "data_quality_log": pd.read_csv(processed_dir / "data_quality_log.csv"),
    }
    excel = outputs_dir / "powerbi_data.xlsx"
    write_workbook(sheets, excel)
    for name, df in sheets.items():
        log.info("%-18s %5d rows", name, len(df))
    log.info("Saved %s", excel)
    return excel


if __name__ == "__main__":
    main()
