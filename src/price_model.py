"""What drives biodiversity credit prices? A regression to measure the scarcity premium, and a
machine learning model to predict the price of a sale, both tested on sales they have not seen.

Run after clean.py and gap_analysis.py:  python src/price_model.py
"""
# STEP 1: Imports, file locations and settings
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from common import (OUTPUTS, PROCESSED, DataValidationError, get_logger, require_columns,
                    require_files)

FIGURES = OUTPUTS / "figures"
log = get_logger("price_model")

MIN_PRICE = 10          # prices below $10 a credit are token amounts, not market prices
TOP_SUBREGIONS = 15     # keep the 15 busiest subregions, group the rest as "Other"
SEED = 42
BANDS = ["None left", "Under 1 year", "1 to 10 years", "Over 10 years", "No retirements"]
CATEGORICAL = ["scarcity_band", "credit_class", "formation", "subregion"]
NUMERIC = ["year", "log_credits"]
FEATURE_LABELS = {"scarcity_band": "Scarcity (years of supply)", "credit_class":
                  "Ecosystem or species", "formation": "Vegetation formation",
                  "subregion": "IBRA subregion", "year": "Year of sale",
                  "log_credits": "Number of credits in the sale"}

BLUE, ORANGE, INK, INK_2, GRID, SURFACE = ("#2a78d6", "#eb6834", "#0b0b0b", "#52514e",
                                           "#e4e3df", "#fcfcfb")
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "DejaVu Sans", "font.size": 10, "text.color": INK, "axes.edgecolor": GRID,
    "axes.labelcolor": INK_2, "axes.titlesize": 13, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.titlepad": 30, "axes.axisbelow": True,
    "xtick.color": INK_2, "ytick.color": INK_2, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "legend.frameon": False,
})


# STEP 2: Build one row per sale with the features the models use
def load_sales(processed_dir: Path = PROCESSED) -> pd.DataFrame:
    tx_path, gap_path = processed_dir / "transactions_clean.csv", processed_dir / "gap_ranking.csv"
    require_files(tx_path, gap_path, hint="Run clean.py and gap_analysis.py first.")
    tx = pd.read_csv(tx_path, parse_dates=["transaction_date"])
    gap = pd.read_csv(gap_path)
    require_columns(tx, ["price_valid", "philanthropic_reason_for_transfer_disclosed",
                         "price_per_credit_ex_gst", "credit_key", "credit_class",
                         "vegetation_formation", "ibra_subregion", "number_of_credits",
                         "transaction_date"], "transactions_clean")
    require_columns(gap, ["credit_key", "years_of_supply"], "gap_ranking")

    # Real market sales only: a valid price, not a disclosed philanthropic transfer
    sales = tx[tx["price_valid"] & (tx["philanthropic_reason_for_transfer_disclosed"] != "Yes")]
    token = sales["price_per_credit_ex_gst"] < MIN_PRICE
    log.info("Sales with a valid price: %d (%d token prices under $%d left out)",
             len(sales), token.sum(), MIN_PRICE)
    sales = sales[~token].copy()

    years = sales["credit_key"].map(gap.set_index("credit_key")["years_of_supply"])
    sales["scarcity_band"] = pd.cut(years, bins=[-0.01, 0, 1, 10, np.inf],
                                    labels=BANDS[:4]).astype(str).replace("nan", BANDS[4])
    sales["formation"] = (sales["vegetation_formation"].str.replace(r"\s*\(.*\)", "", regex=True)
                          .fillna("Species credit"))
    busiest = sales["ibra_subregion"].value_counts().head(TOP_SUBREGIONS).index
    sales["subregion"] = sales["ibra_subregion"].where(sales["ibra_subregion"].isin(busiest),
                                                       "Other")
    sales["year"] = sales["transaction_date"].dt.year
    sales["log_credits"] = np.log(sales["number_of_credits"])
    sales["log_price"] = np.log(sales["price_per_credit_ex_gst"])
    if sales[CATEGORICAL + NUMERIC + ["log_price"]].isna().any().any():
        raise DataValidationError("Some sales are missing a model feature.")
    return sales.reset_index(drop=True)


# STEP 3: Regression - how much more do scarce credits sell for, other things being equal?
# Standard errors are clustered by credit type, because sales of the same type are related.
def scarcity_regression(sales: pd.DataFrame) -> tuple[pd.DataFrame, float, int]:
    formula = ("log_price ~ C(scarcity_band, Treatment('Over 10 years')) + C(credit_class)"
               " + C(formation) + C(subregion) + C(year) + log_credits")
    groups = pd.factorize(sales["credit_key"])[0]
    fit = smf.ols(formula, data=sales).fit(cov_type="cluster", cov_kwds={"groups": groups})
    ci = fit.conf_int()
    rows = []
    for term in fit.params.index:
        if "scarcity_band" in term or term == "log_credits":
            label = term.split("[T.")[-1].rstrip("]") if "[T." in term else "Doubling the credits"
            scale = np.log(2) if term == "log_credits" else 1  # effect of doubling the sale size
            rows.append({"term": label, "coef": fit.params[term], "p_value": fit.pvalues[term],
                         "effect_pct": 100 * (np.exp(scale * fit.params[term]) - 1),
                         "ci_low_pct": 100 * (np.exp(scale * ci.loc[term, 0]) - 1),
                         "ci_high_pct": 100 * (np.exp(scale * ci.loc[term, 1]) - 1)})
    return pd.DataFrame(rows), fit.rsquared, len(np.unique(groups))


# STEP 4: The three models compared
def baseline_predict(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Baseline: the median price of that credit class in that year (what a simple lookup gives)."""
    med = train.groupby(["credit_class", "year"])["log_price"].median()
    fallback = train.groupby("credit_class")["log_price"].median()
    keys = list(zip(test["credit_class"], test["year"]))
    return np.array([med.get(k, fallback[k[0]]) for k in keys])


def linear_model() -> object:
    prep = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
                              ("num", StandardScaler(), NUMERIC)])
    return make_pipeline(prep, RidgeCV(alphas=np.logspace(-2, 3, 20)))


def boosting_model() -> object:
    prep = ColumnTransformer([("cat", OrdinalEncoder(handle_unknown="use_encoded_value",
                                                     unknown_value=-1), CATEGORICAL),
                              ("num", "passthrough", NUMERIC)])
    model = HistGradientBoostingRegressor(categorical_features=list(range(len(CATEGORICAL))),
                                          max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                          min_samples_leaf=20, l2_regularization=1.0,
                                          random_state=SEED)
    return make_pipeline(prep, model)


def scores(name: str, test_set: str, y: np.ndarray, pred: np.ndarray) -> dict:
    """Errors on the log scale, also shown as a typical % error in dollars."""
    pct_error = 100 * np.abs(np.exp(pred - y) - 1)
    return {"model": name, "test": test_set, "n_test": len(y),
            "r2_log_price": r2_score(y, pred), "mae_log_price": mean_absolute_error(y, pred),
            "median_pct_error": np.median(pct_error)}


# STEP 5: Test on unseen data, two ways
# (a) Grouped cross-validation: every sale of a credit type is in the same fold, so the model
#     is always tested on credit types it has never seen.
# (b) Time split: train on 2019-2024, test on 2025-2026, like using the model for real.
def evaluate(sales: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    X, y = sales[CATEGORICAL + NUMERIC], sales["log_price"].to_numpy()
    rows, holdout = [], None
    oof = {m: np.zeros(len(sales)) for m in ["Baseline", "Linear (ridge)", "Gradient boosting"]}
    for train_idx, test_idx in GroupKFold(n_splits=5).split(X, y, groups=sales["credit_key"]):
        tr, te = sales.iloc[train_idx], sales.iloc[test_idx]
        oof["Baseline"][test_idx] = baseline_predict(tr, te)
        oof["Linear (ridge)"][test_idx] = linear_model().fit(X.iloc[train_idx], y[train_idx]).predict(X.iloc[test_idx])
        oof["Gradient boosting"][test_idx] = boosting_model().fit(X.iloc[train_idx], y[train_idx]).predict(X.iloc[test_idx])
    rows += [scores(m, "5-fold, unseen credit types", y, p) for m, p in oof.items()]

    train, test = sales["year"] <= 2024, sales["year"] >= 2025
    preds = {"Baseline": None,  # the baseline has no 2025-26 medians, so use each class's latest year
             "Linear (ridge)": linear_model().fit(X[train], y[train]).predict(X[test]),
             "Gradient boosting": boosting_model().fit(X[train], y[train]).predict(X[test])}
    latest = sales[train].assign(year=2024)
    preds["Baseline"] = baseline_predict(latest, sales[test].assign(year=2024))
    rows += [scores(m, "Train 2019-24, test 2025-26", y[test], p) for m, p in preds.items()]
    holdout = sales[test].assign(predicted_log_price=preds["Gradient boosting"])
    return pd.DataFrame(rows), holdout


# STEP 6: Which features matter most? Permutation importance on each held-out fold of the
# grouped cross-validation, averaged (shuffle one feature, see how much worse the model gets)
def feature_importance(sales: pd.DataFrame) -> pd.DataFrame:
    X, y = sales[CATEGORICAL + NUMERIC], sales["log_price"]
    folds = []
    for train_idx, test_idx in GroupKFold(n_splits=5).split(X, y, groups=sales["credit_key"]):
        model = boosting_model().fit(X.iloc[train_idx], y.iloc[train_idx])
        result = permutation_importance(model, X.iloc[test_idx], y.iloc[test_idx], n_repeats=10,
                                        random_state=SEED, scoring="neg_mean_absolute_error")
        folds.append(result.importances_mean)
    folds = np.array(folds)
    return (pd.DataFrame({"feature": X.columns, "importance": folds.mean(axis=0),
                          "std": folds.std(axis=0)})
            .assign(label=lambda d: d["feature"].map(FEATURE_LABELS))
            .sort_values("importance", ascending=False).reset_index(drop=True))


# STEP 7: Charts
def subtitle(ax: plt.Axes, text: str) -> None:
    ax.text(0, 1.02, text, transform=ax.transAxes, color=INK_2, fontsize=9.5, va="bottom")


def chart_premium(coefs: pd.DataFrame, path: Path) -> None:
    d = coefs[coefs["term"].isin(BANDS)].set_index("term").reindex(
        ["None left", "Under 1 year", "1 to 10 years", "No retirements"]).dropna().iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 3.8))
    y = range(len(d))
    ax.errorbar(d["effect_pct"], y, xerr=[d["effect_pct"] - d["ci_low_pct"],
                                         d["ci_high_pct"] - d["effect_pct"]],
                fmt="o", color=BLUE, ecolor=BLUE, elinewidth=2, capsize=4, markersize=8)
    for yi, (_, r) in zip(y, d.iterrows()):
        ax.text(r["ci_high_pct"] + 3, yi, f"{r['effect_pct']:+.0f}%  (p = {r['p_value']:.3f})",
                va="center", fontsize=9, color=INK_2)
    ax.axvline(0, color=INK_2, lw=1)
    ax.set_yticks(list(y))
    ax.set_yticklabels(d.index)
    ax.set_xlabel("Price difference vs credit types with over 10 years of supply")
    ax.set_xlim(min(-60, d["ci_low_pct"].min() - 10), d["ci_high_pct"].max() + 60)
    ax.set_title("The scarcity premium, after allowing for other factors")
    subtitle(ax, "Regression on 1,276 sales, controlling for year, ecosystem/species, vegetation "
                 "formation, subregion and sale size. Bars = 95% CI.")
    ax.grid(axis="y", visible=False)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def chart_check(holdout: pd.DataFrame, score: dict, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6.5, 6))
    for cls, colour in [("Ecosystem", BLUE), ("Species", ORANGE)]:
        d = holdout[holdout["credit_class"] == cls]
        ax.scatter(np.exp(d["log_price"]), np.exp(d["predicted_log_price"]), s=14, alpha=0.6,
                   color=colour, label=cls, edgecolors="none")
    lims = [50, 50_000]
    ax.plot(lims, lims, color=INK_2, lw=1, ls="--")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(lims)
    ax.set_ylim(lims)
    fmt = matplotlib.ticker.FuncFormatter(lambda v, _: f"${v:,.0f}")
    ax.xaxis.set_major_formatter(fmt)
    ax.yaxis.set_major_formatter(fmt)
    ax.set_xlabel("Actual price per credit")
    ax.set_ylabel("Predicted price per credit")
    ax.set_title("Model check on 2025-26 sales it never saw")
    subtitle(ax, f"Gradient boosting trained on 2019-24.  R² (log) = {score['r2_log_price']:.2f}, "
                 f"typical error {score['median_pct_error']:.0f}%")
    ax.legend(loc="upper left")
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def chart_importance(imp: pd.DataFrame, path: Path) -> None:
    d = imp.iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.barh(d["label"], d["importance"], xerr=d["std"], color=BLUE, height=0.6,
            error_kw={"ecolor": INK_2, "elinewidth": 1})
    ax.set_xlabel("Increase in prediction error when the feature is shuffled (log price)")
    ax.set_title("What drives credit prices?")
    subtitle(ax, "Permutation importance, gradient boosting, averaged over 5 held-out folds")
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", length=0)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


# STEP 8: Run everything and save the results
def main(processed_dir: Path = PROCESSED, figures_dir: Path = FIGURES) -> dict:
    processed_dir, figures_dir = Path(processed_dir), Path(figures_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)
    sales = load_sales(processed_dir)
    coefs, r2, n_types = scarcity_regression(sales)
    model_scores, holdout = evaluate(sales)
    imp = feature_importance(sales)

    coefs.round(4).to_csv(processed_dir / "price_model_coefficients.csv", index=False)
    model_scores.round(4).to_csv(processed_dir / "price_model_scores.csv", index=False)
    imp.round(4).to_csv(processed_dir / "price_model_importance.csv", index=False)

    best = model_scores[(model_scores["model"] == "Gradient boosting")
                        & model_scores["test"].str.startswith("Train")].iloc[0].to_dict()
    chart_premium(coefs, figures_dir / "09_scarcity_premium.png")
    chart_check(holdout, best, figures_dir / "10_price_model_check.png")
    chart_importance(imp, figures_dir / "11_price_drivers.png")

    pd.set_option("display.width", 200)
    log.info("Regression: %d sales, %d credit types, R² = %.2f", len(sales), n_types, r2)
    log.info("Scarcity and sale-size effects:\n%s", coefs.round(3).to_string(index=False))
    log.info("Model scores:\n%s", model_scores.round(3).to_string(index=False))
    log.info("Feature importance:\n%s", imp[["label", "importance"]].round(3).to_string(index=False))
    log.info("Saved price_model_*.csv and charts 09-11")
    return {"sales": sales, "coefs": coefs, "scores": model_scores, "importance": imp}


if __name__ == "__main__":
    main()
