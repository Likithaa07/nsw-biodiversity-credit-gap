# STEP 1: Imports and XML settings
from io import StringIO

import pandas as pd
from lxml import etree

NS = {"ss": "urn:schemas-microsoft-com:office:spreadsheet"}
INDEX = "{urn:schemas-microsoft-com:office:spreadsheet}Index"


# STEP 2: Reusable function to read an XML register into a table
def read_xml_register(path, first_header):
    parser = etree.XMLParser(recover=True, huge_tree=True)
    tree = etree.parse(path, parser)
    sheet = tree.findall(".//ss:Worksheet", NS)[0]  # first sheet = full register

    rows = []
    for row in sheet.findall(".//ss:Row", NS):
        cells = []
        for cell in row.findall("ss:Cell", NS):
            # Empty cells are skipped in the XML; ss:Index tells us the real column
            if cell.get(INDEX):
                while len(cells) < int(cell.get(INDEX)) - 1:
                    cells.append(None)
            data = cell.find("ss:Data", NS)
            cells.append("".join(data.itertext()) if data is not None else None)
        rows.append(cells)

    header_index = next(i for i, r in enumerate(rows) if r and r[0] == first_header)
    columns = rows[header_index]
    width = len(columns)
    data_rows = [(r + [None] * width)[:width] for r in rows[header_index + 1:]]
    return pd.DataFrame(data_rows, columns=columns).dropna(how="all")


# STEP 3: Reusable function to read an HTML register into a table
def read_html_register(path):
    with open(path, encoding="utf-8") as f:
        html = f.read()
    tables = pd.read_html(StringIO(html))
    table = max(tables, key=len)  # the data table is the biggest one on the page
    # Transaction IDs are saved as Excel formulas like ="00018450", so strip that
    table["Transaction ID"] = table["Transaction ID"].astype(str).str.strip('="')
    return table


# STEP 4: Test - load all three registers (only runs when this file is run directly)
if __name__ == "__main__":
    pd.set_option("display.width", 200)

    demand = read_xml_register("data/raw/Demand.xls", "Credit status")
    supply = read_xml_register("data/raw/Supply.xls", "Credit ID")
    transactions = read_html_register("data/raw/Transactions.xls")

    print("Demand:", demand.shape)
    print("Supply:", supply.shape)
    print("Transactions:", transactions.shape)
    print(transactions[["Transaction Date", "Transaction ID", "Transaction Type",
                        "Number Of Credits", "Price Per Credit (Ex-Gst)"]].head())