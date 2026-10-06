# STEP 1: Imports and file locations
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"


# STEP 2: Read a BioBanking report export (real .xls, with blank spacer columns)
def read_biobanking(path, first_header, wanted):
    sheet = pd.read_excel(path, header=None, engine="xlrd")
    header_row = sheet.index[sheet.iloc[:, 1].astype(str).str.strip() == first_header][0]
    header = sheet.loc[header_row]
    body = sheet.loc[header_row + 1:]
    table = {}
    for label, name in wanted.items():
        col = header.index[header.astype(str).str.replace(r"\s+", " ", regex=True).str.strip() == label][0]
        table[name] = body[col]
    table = pd.DataFrame(table)
    table["credits"] = pd.to_numeric(table["credits"], errors="coerce")
    return table.dropna(subset=["credits"])  # drops title, footer and page-number rows


species = read_biobanking(RAW / "BioBanking_Species.xls", "Credit owner(s)",
                          {"Scientific name": "species_scientific_name",
                           "Common name": "species_common_name",
                           "Credit status": "credit_status", "Credits": "credits"})
ecosystem = read_biobanking(RAW / "BioBanking_Ecosystem.xls", "Credit owner(s)",
                            {"Plant Community Code": "vegetation_code",
                             "IBRA sub-region": "ibra_subregion",
                             "Credit Status": "credit_status", "Credits": "credits"})


# STEP 3: Match BioBanking species credits to the BOS scarcity ranking by scientific name
def simplify(names):
    return (names.astype(str).str.lower().str.replace("var.", "subsp.", regex=False)
            .str.replace(r"\s+", " ", regex=True).str.strip())


biobanking_by_species = species.groupby(simplify(species["species_scientific_name"]))["credits"].sum()

gap = pd.read_csv(PROCESSED / "gap_ranking.csv")
check = gap[gap["credit_class"] == "Species"].copy()
check["biobanking_credits"] = simplify(check["credit_key"]).map(biobanking_by_species).fillna(0)
check = check[["scarcity_rank", "credit_name", "available_credits", "retired_per_year",
               "years_of_supply", "biobanking_credits"]]
check.to_csv(PROCESSED / "biobanking_species_check.csv", index=False)


# STEP 4: Print a summary
scarce = check[check["years_of_supply"] < 1]
print(f"BioBanking species credits: {len(species)} holdings, {species['credits'].sum():,.0f} credits")
print(f"BioBanking ecosystem credits: {len(ecosystem)} holdings, {ecosystem['credits'].sum():,.0f} credits")
print("  (ecosystem credits use old vegetation codes such as "
      f"{ecosystem['vegetation_code'].iloc[0]}, which cannot be matched to PCT IDs)")
print(f"\nScarce species (under 1 year of supply): {len(scarce)}")
print(f"  with any BioBanking credits: {(scarce['biobanking_credits'] > 0).sum()}")
pd.set_option("display.width", 200)
out = scarce.copy()
out["credit_name"] = out["credit_name"].str[:55]
print(out.round(1).to_string(index=False))
print(f"\nSaved to {PROCESSED / 'biobanking_species_check.csv'}")
