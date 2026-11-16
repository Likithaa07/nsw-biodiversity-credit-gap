"""Cross-check the scarce species against the pre-2017 BioBanking credit registers."""
# STEP 1: Imports and file locations
from __future__ import annotations

from pathlib import Path

import pandas as pd

from common import (PROCESSED, RAW, DataValidationError, get_logger, require_columns,
                    require_files)

log = get_logger("biobanking_check")

SPECIES_COLUMNS = {"Scientific name": "species_scientific_name",
                   "Common name": "species_common_name",
                   "Credit status": "credit_status", "Credits": "credits"}
ECOSYSTEM_COLUMNS = {"Plant Community Code": "vegetation_code",
                     "IBRA sub-region": "ibra_subregion",
                     "Credit Status": "credit_status", "Credits": "credits"}


# STEP 2: Read a BioBanking report export (real .xls, with blank spacer columns)
def read_biobanking(path: str | Path, first_header: str,
                    wanted: dict[str, str]) -> pd.DataFrame:
    """Find the header row by its label, then pick columns by label (not by position)."""
    require_files(Path(path))
    sheet = pd.read_excel(path, header=None, engine="xlrd")
    header_rows = sheet.index[sheet.iloc[:, 1].astype(str).str.strip() == first_header]
    if len(header_rows) == 0:
        raise DataValidationError(f"{Path(path).name}: header row '{first_header}' not found.")
    header_row = header_rows[0]
    header = sheet.loc[header_row].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    body = sheet.loc[header_row + 1:]
    table = {}
    for label, name in wanted.items():
        matches = header.index[header == label]
        if len(matches) == 0:
            raise DataValidationError(f"{Path(path).name}: column '{label}' not found.")
        table[name] = body[matches[0]]
    table = pd.DataFrame(table)
    table["credits"] = pd.to_numeric(table["credits"], errors="coerce")
    return table.dropna(subset=["credits"])  # drops title, footer and page-number rows


# STEP 3: Simplify scientific names so the two registers match ("var." vs "subsp.")
def simplify(names: pd.Series) -> pd.Series:
    return (names.astype(str).str.lower().str.replace("var.", "subsp.", regex=False)
            .str.replace(r"\s+", " ", regex=True).str.strip())


# STEP 4: Match BioBanking species credits to the BOS scarcity ranking by scientific name
def match_species(species: pd.DataFrame, gap: pd.DataFrame) -> pd.DataFrame:
    by_species = species.groupby(simplify(species["species_scientific_name"]))["credits"].sum()
    check = gap[gap["credit_class"] == "Species"].copy()
    check["biobanking_credits"] = simplify(check["credit_key"]).map(by_species).fillna(0)
    return check[["scarcity_rank", "credit_name", "available_credits", "retired_per_year",
                  "years_of_supply", "biobanking_credits"]]


# STEP 5: Run, save and log a summary
def main(raw_dir: Path = RAW, processed_dir: Path = PROCESSED) -> pd.DataFrame:
    gap_path = Path(processed_dir) / "gap_ranking.csv"
    require_files(gap_path, hint="Run gap_analysis.py first.")
    species = read_biobanking(Path(raw_dir) / "BioBanking_Species.xls", "Credit owner(s)",
                              SPECIES_COLUMNS)
    ecosystem = read_biobanking(Path(raw_dir) / "BioBanking_Ecosystem.xls", "Credit owner(s)",
                                ECOSYSTEM_COLUMNS)
    gap = pd.read_csv(gap_path)
    require_columns(gap, ["scarcity_rank", "credit_class", "credit_key", "credit_name",
                          "available_credits", "retired_per_year", "years_of_supply"],
                    "gap_ranking")

    check = match_species(species, gap)
    check.to_csv(Path(processed_dir) / "biobanking_species_check.csv", index=False)

    scarce = check[check["years_of_supply"] < 1]
    out = scarce.copy()
    out["credit_name"] = out["credit_name"].str[:55]
    pd.set_option("display.width", 200)
    log.info("BioBanking species credits: %d holdings, %s credits",
             len(species), f"{species['credits'].sum():,.0f}")
    log.info("BioBanking ecosystem credits: %d holdings, %s credits (old vegetation codes such "
             "as %s, which cannot be matched to PCT IDs)", len(ecosystem),
             f"{ecosystem['credits'].sum():,.0f}", ecosystem["vegetation_code"].iloc[0])
    log.info("Scarce species (under 1 year of supply): %d, with any BioBanking credits: %d\n%s",
             len(scarce), (scarce["biobanking_credits"] > 0).sum(),
             out.round(1).to_string(index=False))
    log.info("Saved to %s", Path(processed_dir) / "biobanking_species_check.csv")
    return check


if __name__ == "__main__":
    main()
