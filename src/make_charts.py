# STEP 1: Imports, file locations and chart style
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "outputs" / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"   # validated colour-blind-safe set
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
SCARCITY_RAMP = ["#104281", "#256abf", "#5598e7", "#9ec5f4"]  # dark = scarcer
CLASS_COLOURS = {"Ecosystem": BLUE, "Species": ORANGE}

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "DejaVu Sans", "font.size": 10, "text.color": INK,
    "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "axes.titlesize": 13,
    "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.titlepad": 30, "axes.axisbelow": True,
    "xtick.color": INK_2, "ytick.color": INK_2, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "legend.frameon": False,
})

gap = pd.read_csv(PROCESSED / "gap_ranking.csv")
price_year = pd.read_csv(PROCESSED / "price_by_year.csv")
price_scarcity = pd.read_csv(PROCESSED / "price_by_scarcity.csv")
quality = pd.read_csv(PROCESSED / "data_quality_log.csv")
transactions = pd.read_csv(PROCESSED / "transactions_clean.csv", parse_dates=["transaction_date"])


def subtitle(ax, text):
    ax.text(0, 1.02, text, transform=ax.transAxes, color=INK_2, fontsize=9.5, va="bottom")


def save(fig, name):
    fig.savefig(FIGURES / name, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("saved", name)


# STEP 2: Chart 1 - the 15 scarcest credit types
top = gap.head(15).iloc[::-1].copy()
top["label"] = top["credit_name"].str.slice(0, 62).where(
    top["credit_name"].str.len() <= 62, top["credit_name"].str.slice(0, 60) + "…")
fig, ax = plt.subplots(figsize=(11, 6.5))
bars = ax.barh(top["label"], top["retired_per_year"], height=0.62,
               color=[CLASS_COLOURS[c] for c in top["credit_class"]])
for bar, avail in zip(bars, top["available_credits"]):
    ax.text(bar.get_width() + 6, bar.get_y() + bar.get_height() / 2,
            f"{bar.get_width():,.0f} / yr  ·  {avail:,.0f} available",
            va="center", fontsize=8.5, color=INK_2)
ax.set_xlabel("Credits retired per year (Nov 2019 – Oct 2026 average)")
ax.set_title("The 15 most under-supplied biodiversity credit types in NSW")
subtitle(ax, "Ranked by years of supply left. All 15 have no credits available to buy.")
ax.grid(axis="y", visible=False)
ax.set_xlim(0, top["retired_per_year"].max() * 1.45)
ax.tick_params(axis="y", labelsize=8.5, length=0)
shown = [c for c in CLASS_COLOURS if c in set(top["credit_class"])]
if len(shown) > 1:
    handles = [plt.Rectangle((0, 0), 1, 1, color=CLASS_COLOURS[c]) for c in shown]
    ax.legend(handles, shown, loc="lower right")
save(fig, "01_top15_scarcest.png")


# STEP 3: Chart 2 - how many credit types fall in each scarcity band
bands = pd.cut(gap["years_of_supply"], bins=[-0.01, 0, 1, 10, float("inf")],
               labels=["None left", "Under 1 year", "1–10 years", "Over 10 years"])
counts = bands.value_counts().reindex(bands.cat.categories)
fig, ax = plt.subplots(figsize=(8, 4.2))
bars = ax.bar(counts.index.astype(str), counts.values, color=SCARCITY_RAMP, width=0.6)
for bar in bars:
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 3, f"{bar.get_height():.0f}",
            ha="center", fontsize=11, fontweight="bold")
ax.set_ylabel("Number of credit types")
ax.set_title("Years of supply left, across 305 credit types in demand")
subtitle(ax, "Years of supply = credits available ÷ credits retired per year")
ax.grid(axis="x", visible=False)
ax.set_ylim(0, counts.max() * 1.18)
save(fig, "02_scarcity_bands.png")


# STEP 4: Chart 3 - median price per credit over time
fig, ax = plt.subplots(figsize=(9, 4.6))
for cls, colour in CLASS_COLOURS.items():
    d = price_year[price_year["credit_class"] == cls].sort_values("year")
    ax.plot(d["year"], d["median_price"], color=colour, linewidth=2.2, marker="o", markersize=7,
            markeredgecolor=SURFACE, markeredgewidth=1.5)
    last = d.iloc[-1]
    ax.text(last["year"] + 0.15, last["median_price"], f"{cls}\n${last['median_price']:,.0f}",
            color=INK, fontsize=9, va="center")
ax.axvspan(2018.6, 2020.5, color=GRID, alpha=0.5, linewidth=0)
ax.text(2019.55, price_year["median_price"].max() * 1.1, "few sales\n(≤10 a year)", ha="center", fontsize=8,
        color=INK_2)
ax.set_xlim(2018.6, 2027.2)
ax.set_ylim(0, price_year["median_price"].max() * 1.2)
ax.set_xticks(range(2019, 2027))
ax.set_xticklabels([str(y) if y < 2026 else "2026*" for y in range(2019, 2027)])
ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("${x:,.0f}"))
ax.set_ylabel("Price per credit (ex GST)")
ax.set_title("Median price per credit by year")
subtitle(ax, "Median sale price, excluding $0 and philanthropic transfers.  *2026 is January–October only.")
ax.grid(axis="x", visible=False)
save(fig, "03_price_trend.png")


# STEP 5: Chart 4 - do scarcer credit types cost more?
order = ["0 years (none left)", "Under 1 year", "1 to 10 years", "Over 10 years"]
fig, ax = plt.subplots(figsize=(9, 4.4))
width = 0.36
for i, (cls, colour) in enumerate(CLASS_COLOURS.items()):
    d = price_scarcity[price_scarcity["credit_class"] == cls].set_index("scarcity_band").reindex(order)
    x = [j + (i - 0.5) * width for j in range(len(order))]
    bars = ax.bar(x, d["median_price"].fillna(0), width=width - 0.04, color=colour, label=cls)
    for bar, n, p in zip(bars, d["credit_types"], d["median_price"]):
        if pd.notna(p):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 80,
                    f"${p:,.0f}\nn={n:.0f}", ha="center", fontsize=8, color=INK_2)
ax.set_xticks(range(len(order)))
ax.set_xticklabels(["None left", "Under 1 year", "1–10 years", "Over 10 years"])
ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("${x:,.0f}"))
ax.set_ylabel("Median price per credit")
ax.set_title("Scarcer credit types generally sell for more")
subtitle(ax, "Median of each credit type's median sale price.  n = number of credit types.")
ax.set_ylim(0, price_scarcity["median_price"].max() * 1.25)
ax.grid(axis="x", visible=False)
ax.legend(loc="upper right")
save(fig, "04_price_by_scarcity.png")


# STEP 6: Chart 5 - credits retired each year (demand over time)
ret = transactions[transactions["transaction_type"] == "Retire"].copy()
ret["year"] = ret["transaction_date"].dt.year
by_year = ret.pivot_table(index="year", columns="credit_class", values="number_of_credits",
                          aggfunc="sum").fillna(0).reindex(columns=list(CLASS_COLOURS))
fig, ax = plt.subplots(figsize=(9, 4.4))
width = 0.38
for i, (cls, colour) in enumerate(CLASS_COLOURS.items()):
    x = [y + (i - 0.5) * width for y in by_year.index]
    ax.bar(x, by_year[cls], width=width - 0.04, color=colour, label=cls)
ax.set_xticks(by_year.index)
ax.set_xticklabels([str(y) if y < 2026 else "2026*" for y in by_year.index])
ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.0f}"))
ax.set_ylabel("Credits retired")
ax.set_title("Credits retired to meet offset obligations, by year")
subtitle(ax, f"{ret['number_of_credits'].sum():,.0f} credits retired in total.  *2026 is January–October only.")
ax.grid(axis="x", visible=False)
ax.legend(loc="upper left")
save(fig, "05_retirements_by_year.png")


# STEP 7: Chart 6 - data quality: issues found and what was done
q = quality[(quality["rows_affected"] > 0) & ~quality["check"].str.startswith("Personal")
            & ~quality["check"].str.startswith("Register has")].copy()
q["label"] = (q["dataset"].str.capitalize() + ": " + q["check"]).str.replace(
    r" \(.*\)", "", regex=True)
q["kind"] = q["action"].str.extract(r"^(Dropped|Fixed|Converted|Replaced|Set to missing|Kept)",
                                    expand=False).replace(
    {"Converted": "Fixed", "Replaced": "Fixed", "Set to missing": "Fixed"})
q["kind"] = q["kind"].replace({"Kept": "Kept & flagged", "Dropped": "Dropped"})
kind_colours = {"Fixed": BLUE, "Kept & flagged": ORANGE, "Dropped": AQUA}
q = q.sort_values("rows_affected")
fig, ax = plt.subplots(figsize=(10, 5))
bars = ax.barh(q["label"], q["rows_affected"], color=[kind_colours[k] for k in q["kind"]],
               height=0.6)
for bar in bars:
    ax.text(bar.get_width() * 1.15, bar.get_y() + bar.get_height() / 2,
            f"{bar.get_width():,.0f}", va="center", fontsize=8.5, color=INK_2)
ax.set_xscale("log")
ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
ax.set_xlim(1, q["rows_affected"].max() * 8)
ax.set_xlabel("Rows or cells affected (log scale)")
ax.set_title("Data quality issues found and how each was handled")
subtitle(ax, "Every issue is logged by clean.py in data_quality_log.csv")
ax.grid(axis="y", visible=False)
ax.tick_params(axis="y", labelsize=8.5, length=0)
handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in kind_colours.values()]
ax.legend(handles, kind_colours.keys(), loc="lower right")
save(fig, "06_data_quality_issues.png")


# STEP 8: Chart 7 - years of supply by region (subregion)
region = pd.read_csv(PROCESSED / "gap_by_region.csv").head(12).iloc[::-1]
region["label"] = region["ibra_subregion"] + "  (" + region["ibra_region"].fillna("—") + ")"
colours = [SCARCITY_RAMP[0] if y < 2 else SCARCITY_RAMP[1] if y < 5 else SCARCITY_RAMP[2]
           for y in region["years_of_supply"]]
fig, ax = plt.subplots(figsize=(10, 5.2))
bars = ax.barh(region["label"], region["years_of_supply"], color=colours, height=0.6)
for bar, avail, used in zip(bars, region["available_credits"], region["retired_per_year"]):
    ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
            f"{bar.get_width():.1f} yrs   ({avail:,.0f} available, {used:,.0f} used / yr)",
            va="center", fontsize=8.5, color=INK_2)
ax.set_xlim(0, region["years_of_supply"].max() * 1.9)
ax.set_xlabel("Years of supply left (all credit types in the subregion pooled)")
ax.set_title("Subregions where offset supply is tightest")
subtitle(ax, "IBRA subregions with at least 50 credits retired a year, scarcest first")
ax.grid(axis="y", visible=False)
ax.tick_params(axis="y", labelsize=8.5, length=0)
save(fig, "07_scarcity_by_region.png")


# STEP 9: Chart 8 - market value of credit sales by year
sales = transactions[transactions["price_valid"]
                     & (transactions["philanthropic_reason_for_transfer_disclosed"] != "Yes")].copy()
sales["value_m"] = sales["price_per_credit_ex_gst"] * sales["number_of_credits"] / 1e6
value = sales.groupby(sales["transaction_date"].dt.year)["value_m"].sum()
fig, ax = plt.subplots(figsize=(9, 4.4))
bars = ax.bar(value.index, value.values, color=BLUE, width=0.6)
for bar in bars:
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 3, f"${bar.get_height():,.0f}M",
            ha="center", fontsize=9, color=INK)
ax.set_xticks(value.index)
ax.set_xticklabels([str(y) if y < 2026 else "2026*" for y in value.index])
ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("${x:,.0f}M"))
ax.set_ylabel("Value of credit sales (ex GST)")
ax.set_title("Value of biodiversity credit sales by year")
subtitle(ax, f"${value.sum():,.0f} million in total since 2019.  *2026 is January–October only.")
ax.set_ylim(0, value.max() * 1.15)
ax.grid(axis="x", visible=False)
save(fig, "08_market_value_by_year.png")
