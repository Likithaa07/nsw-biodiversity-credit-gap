"""Readers for the BOS register exports, which are saved as '.xls' but are really XML or HTML."""
# STEP 1: Imports and XML settings
from __future__ import annotations

from io import StringIO
from pathlib import Path

import pandas as pd
from lxml import etree

from common import DataValidationError, RAW, get_logger, require_files

NS = {"ss": "urn:schemas-microsoft-com:office:spreadsheet"}
INDEX = "{urn:schemas-microsoft-com:office:spreadsheet}Index"
log = get_logger("readers")


# STEP 2: Reusable function to read an XML register into a table
def read_xml_register(path: str | Path, first_header: str) -> pd.DataFrame:
    """Read a SpreadsheetML (XML) register export.

    The exports contain unescaped '&' characters, title rows above the header and skipped
    empty cells, so this parses in recovery mode, rebuilds skipped cells from ss:Index and
    finds the real header row by its first column name.
    """
    require_files(Path(path))
    parser = etree.XMLParser(recover=True, huge_tree=True)
    tree = etree.parse(str(path), parser)
    sheets = tree.findall(".//ss:Worksheet", NS)
    if not sheets:
        raise DataValidationError(f"{Path(path).name}: no worksheet found. Is this the right export?")
    sheet = sheets[0]  # first sheet = full register

    rows: list[list[str | None]] = []
    for row in sheet.findall(".//ss:Row", NS):
        cells: list[str | None] = []
        for cell in row.findall("ss:Cell", NS):
            # Empty cells are skipped in the XML; ss:Index tells us the real column
            if cell.get(INDEX):
                while len(cells) < int(cell.get(INDEX)) - 1:
                    cells.append(None)
            data = cell.find("ss:Data", NS)
            cells.append("".join(data.itertext()) if data is not None else None)
        rows.append(cells)

    header_index = next((i for i, r in enumerate(rows) if r and r[0] == first_header), None)
    if header_index is None:
        raise DataValidationError(
            f"{Path(path).name}: header row starting with '{first_header}' not found.")
    columns = rows[header_index]
    width = len(columns)
    data_rows = [(r + [None] * width)[:width] for r in rows[header_index + 1:]]
    return pd.DataFrame(data_rows, columns=columns).dropna(how="all")


# STEP 3: Reusable function to read an HTML register into a table
def read_html_register(path: str | Path) -> pd.DataFrame:
    """Read an HTML-table register export (the transactions register)."""
    require_files(Path(path))
    with open(path, encoding="utf-8") as f:
        html = f.read()
    if "<table" not in html.lower():
        raise DataValidationError(f"{Path(path).name}: no HTML table found.")
    try:
        tables = pd.read_html(StringIO(html))
    except ValueError as exc:  # pandas raises ValueError when no table is found
        raise DataValidationError(f"{Path(path).name}: no HTML table found.") from exc
    table = max(tables, key=len)  # the data table is the biggest one on the page
    if "Transaction ID" not in table.columns:
        raise DataValidationError(f"{Path(path).name}: no 'Transaction ID' column.")
    # Transaction IDs are saved as Excel formulas like ="00018450", so strip that
    table["Transaction ID"] = table["Transaction ID"].astype(str).str.strip('="')
    return table


# STEP 4: Quick check - load all three registers (only runs when this file is run directly)
if __name__ == "__main__":
    demand = read_xml_register(RAW / "Demand.xls", "Credit status")
    supply = read_xml_register(RAW / "Supply.xls", "Credit ID")
    transactions = read_html_register(RAW / "Transactions.xls")
    log.info("Demand: %s  Supply: %s  Transactions: %s",
             demand.shape, supply.shape, transactions.shape)
