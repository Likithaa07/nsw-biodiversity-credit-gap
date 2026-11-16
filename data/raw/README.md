# Raw data

These files are the public registers exactly as exported. They are never edited by hand.

| File | Source | Exported | Records |
|---|---|---|---:|
| `Supply.xls` | [BOS public registers](https://www.environment.nsw.gov.au/topics/animals-and-plants/biodiversity-offsets-scheme/maps-systems-and-resources/public-registers): Credit Supply Register | 5 Oct 2026 | 2,861 |
| `Demand.xls` | BOS public registers: Credit Demand Register | 5 Oct 2026 | 0 |
| `Transactions.xls` | BOS public registers: Credit Transactions Register | 5 Oct 2026 | 2,556 |
| `BioBanking_Species.xls` | [BioBanking public registers](https://www.environment.nsw.gov.au/bimsprapp/BiobankingPR.aspx): species credits | 6 Oct 2026 | 200 |
| `BioBanking_Ecosystem.xls` | BioBanking public registers: ecosystem credits | 6 Oct 2026 | 637 |

**Publisher:** NSW Department of Climate Change, Energy, the Environment and Water (DCCEEW).

**Licence:** © State of New South Wales (DCCEEW), licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

**How to refresh:** open each register, run a search with no filters, export every record,
and save it here with the same file name. Then run `python src/run_all.py`. The full steps
are in the [refresh guide](../../outputs/reports/04_Refresh_Guide.pdf).

**Note:** the files are named `.xls`, but `Supply.xls` and `Demand.xls` are SpreadsheetML (XML)
and `Transactions.xls` is an HTML table. `src/readers.py` reads them as they are.
