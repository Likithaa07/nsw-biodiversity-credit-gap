# NSW Biodiversity Credit Market: Gap Analysis & Data Quality Pipeline

Which biodiversity credits are running out in NSW? This project cleans the public
Biodiversity Offsets Scheme (BOS) registers published by DCCEEW, measures how fast each
credit type is being used compared with how many are still available, and ranks the
credit types from most to least under-supplied.

| 📊 [Power BI dashboard](outputs/dashboard.pdf) | 📄 [Findings report](outputs/reports/01_Findings_Report.pdf) | 🧹 [Data quality report](outputs/reports/02_Data_Quality_Report.pdf) | 📖 [Data dictionary](outputs/reports/03_Data_Dictionary.pdf) | 🔄 [Refresh guide](outputs/reports/04_Refresh_Guide.pdf) |
|---|---|---|---|---|

## Key findings (data extracted 5 October 2026)

- **305 credit types** were retired against offset obligations between Nov 2019 and Oct 2026.
- **43 of them have zero credits available** to buy today (39 ecosystem, 4 species).
- **71 have less than one year of supply left** at the average rate of use (the 43 with none
  left, plus 28 more).
- The scarcest credit types are woodlands and dry forests of the **NSW South Western Slopes**
  and the **Hunter**. The top-ranked type, *Black Cypress Pine – Red Stringybark low open
  forest*, is retired at about 507 credits a year and none are available.
- **The pipeline won't fix it.** Only 16 of the 71 scarcest credit types have any credits
  under review, so about 4 in 5 have nothing coming.
- **Demand is surging.** Credits retired rose from about 2,000 in 2021 to about 123,000 in
  2025, and credit sales are worth about **$726 million** since 2019.
- **The tightest subregion is Lower Slopes** (NSW South Western Slopes), with about 1.1 years
  of supply when all credit types are pooled.
- Prices broadly support the ranking. Ecosystem credit types with no supply left sell for a
  median of about $5,400 per credit, against about $3,850 for plentiful types. Median
  species credit prices have risen from about $330 (2020) to $800–900 (2024–2026).

| Rank | Credit type | Available | Retired per year |
|---:|---|---:|---:|
| 1 | Black Cypress Pine – Red Stringybark – red gum – box low open forest (SW Slopes) | 0 | 507 |
| 2 | Red Stringybark – Red Box – Long-leaved Box – Inland Scribbly Gum forest (SW Slopes) | 0 | 289 |
| 3 | Canegrass swamp tall grassland wetland (inland plains) | 0 | 155 |
| 4 | Northern Swamp Mahogany – Bottlebrush Swamp Forest | 0 | 153 |
| 5 | Narrow-leaved Ironbark – Grey Box – Spotted Gum woodland (central & lower Hunter) | 0 | 137 |

Full ranking: `data/processed/gap_ranking.csv` (created when you run the pipeline).

## Data

All data comes from the DCCEEW [Biodiversity Offsets Scheme public registers](https://www.environment.nsw.gov.au/topics/animals-and-plants/biodiversity-offsets-scheme/maps-systems-and-resources/public-registers):

| Register | Rows | Used for |
|---|---:|---|
| Credit Supply Register | 2,861 | Credits available now (Issued, Equivalence) and in the pipeline (Pending Review) |
| Credit Transactions Register | 2,556 | Retirements (demand) and transfers with prices |
| Credit Demand Register | 0 | Empty at extraction, so retirements are used as the demand measure |

Field definitions follow the [BOS public registers user guide](https://www.environment.nsw.gov.au/sites/default/files/biodiversity-offset-scheme-public-registers-user-guide-230238.pdf).
The raw files are **not** included in this repository because they contain personal contact
details. See the [refresh guide](outputs/reports/04_Refresh_Guide.pdf) to download them.

**Licence and attribution:** register data © State of New South Wales (DCCEEW), licensed
under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

## How to run it

Requirements: Python 3.10+.

```bash
pip install -r requirements.txt
# put Supply.xls, Demand.xls and Transactions.xls in data/raw/
python src/clean.py           # clean the registers and write the data quality log
python src/gap_analysis.py    # supply vs demand ranking, by credit type and by region
python src/price_trends.py    # prices by year and by scarcity
python src/export_powerbi.py  # one Excel file for the Power BI dashboard
python src/make_charts.py     # the charts in outputs/figures
```

## Method

1. **Read.** The `.xls` downloads are really Excel 2003 XML and HTML, so `src/readers.py`
   parses them directly, skipping title rows, recovering from broken `&` characters and
   restoring skipped empty cells.
2. **Clean.** `src/clean.py` standardises column names, removes personal contact columns,
   trims whitespace, fixes curly apostrophes and mixed date formats, converts types, and logs
   every issue found and the action taken.
3. **Match.** Ecosystem credits are matched on a simplified Plant Community Type (PCT) name,
   because the two registers spell some names differently. Species credits are matched on
   scientific name.
4. **Gap.** For each credit type:
   - available = Issued + Equivalence credits in the supply register
   - demand = credits retired per year (total retired ÷ 6.8 years of transactions)
   - **years of supply = available ÷ retired per year**. Fewer years means scarcer.
5. **Prices.** The median price per credit (ex GST), using transfers with a real price and
   excluding $0 and disclosed philanthropic transfers. Medians are used because a few very
   large sales would distort an average.

## Data quality

The main issues were 46,418 blank cells hidden as whitespace, 640 curly apostrophes that
broke name matching, 11 dates in a second format, 35 expressions of interest with no credit
numbers, and 222 transactions whose PCT name did not appear in the supply register. Of those
222, 95 were fixed by name matching and 127 are credit types with no supply left.

Full details: [data quality report](outputs/reports/02_Data_Quality_Report.pdf) and
[data dictionary](outputs/reports/03_Data_Dictionary.pdf).

## How this compares with official reviews

| Source | What it found | How it relates to this project |
|---|---|---|
| [NSW Audit Office, *Effectiveness of the Biodiversity Offsets Scheme* (Aug 2022)](https://www.audit.nsw.gov.au/our-work/reports/effectiveness-of-the-biodiversity-offsets-scheme) | 91% of ecosystem and 96% of species credit demand could not be matched to supply; most credit types had never traded; the BCT had met only about 20% of the obligations it took on; public registers lacked key data | Same direction as the finding that 71 of 305 credit types have under a year of supply. The Audit Office figures are higher because they include **all** obligations, including unmet ones held by the BCT, while this project only sees demand that was met (retirements). |
| [IPART, *Biodiversity Credits Market Monitoring 2024–25* (Jul 2026)](https://www.ipart.nsw.gov.au/documents/final-report/annual-report-2024-25-biodiversity-credits-market-monitoring-july-2026) | About 40% of biodiversity types face offsetting difficulties; over a third of BCT settlements in 2024–25 did not follow like-for-like matching; data transparency problems remain | Consistent with the shortage ranking and the data quality issues found here (inconsistent names, no PCT ID in transactions, mislabelled file formats). |
| [Henry Review of the BC Act (Aug 2023)](https://www.newcastleherald.com.au/story/8331389/biodiversity-laws-not-achieving-primary-purpose-ken-henry) | The Act is "not meeting its primary purpose"; 58 recommendations, including an overhaul of the Offsets Scheme | Policy context for why credit shortages matter. |

**Takeaway:** the results here are consistent with official findings, and are best read as a
*conservative lower bound* on scarcity.

## Limitations

- **Demand is measured from retirements**, which is demand that was met. Unmet demand
  (developers who could not find credits and paid into the Biodiversity Conservation Fund
  instead) is not visible, so true scarcity is probably higher than shown.
- **Demand is growing fast.** Retirements rose from about 2,000 credits in 2021 to about
  120,000 in 2025. Averaging over the full 6.8 years therefore understates current demand,
  so the years-of-supply figures are, if anything, optimistic.
- **Point-in-time snapshot.** Supply changes daily, and the results reflect 5 Oct 2026.
- **Like-for-like is simplified.** Each PCT is treated as its own market. Real offset rules
  allow some substitution within offset trading groups and through variation rules, so some
  "zero supply" types may be partly covered by similar credits.
- **Zero supply can reflect one-off deals.** A stewardship site created for one development
  and then fully retired will show as zero supply.
- **Old and new vegetation classifications.** NSW introduced a new eastern NSW PCT
  classification in 2022 (IDs 3000 and above). The same vegetation can appear under an old
  name in one register and a new name in another, so a few "zero supply" types may have
  equivalent credits listed under the new classification.
- **What the region view measures.** The subregion in the transactions register is where the
  credits were located (the stewardship site), not where the development happened. The region
  chart shows where supply is being used up, not where impacts occurred.
- **One-off projects inflate some rates.** For example, the Tarengo Leek Orchid and Pine Donkey
  Orchid figures (503 credits a year each) come from a single project (SSD 8642) that
  retired both species together in June 2024. Averaging a one-off obligation as a yearly rate
  overstates ongoing demand for those species.
- **The BioBanking (pre-2017) registers are not yet included**, except where BioBanking
  credits appear as "Equivalence" credits in the BOS supply register.

## Policy context

Under the NSW [Biodiversity Conservation Act 2016](https://legislation.nsw.gov.au/view/html/inforce/current/act-2016-063),
developments that clear native vegetation must offset their impact by retiring biodiversity
credits on a like-for-like basis, or by paying into the Biodiversity Conservation Fund. Credit
types with no supply push proponents towards fund payments and variation rules. They also
point to where new stewardship sites would be most valuable.

## Repository structure

```
data/raw/          original register downloads (not committed)
data/processed/    cleaned data and results (not committed)
src/               Python pipeline: readers, clean, gap_analysis, price_trends, export_powerbi, make_charts
outputs/           dashboard PDF, report PDFs (reports/), charts (figures/), Power BI data file
```

## Author

Likitha Vankadoth
