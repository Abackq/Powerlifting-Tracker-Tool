import pandas as pd
from sklearn.linear_model import LinearRegression
from prepare import load_sets, add_recent_strength, add_baselines
import numpy as np

TRAIN_FRAC = 0.7   # first 70% of weeks train the model, last 30% test it


def split_by_time(df, train_frac=TRAIN_FRAC):
    """Time-ordered split: the model never trains on weeks that come after the ones it's tested on."""
    cutoff = df["week_index"].quantile(train_frac)
    return df[df["week_index"] <= cutoff], df[df["week_index"] > cutoff]


def fit_corrections(train):
    """One small linear model per lift: actual load ~ formula prediction + RPE.
    The RPE term lets it learn how much the formula over-/understates at each effort level."""
    return {lift: LinearRegression().fit(g[["pred_formula", "rpe"]], g["weight_kgs"])
            for lift, g in train.groupby("lift")}


def predict_model(df, models):
    out = pd.Series(index=df.index, dtype=float)
    for lift, g in df.groupby("lift"):
        out[g.index] = models[lift].predict(g[["pred_formula", "rpe"]])
    return out


def score(name, actual, pred):
    err = (pred - actual).abs()
    print(f"{name:<14} n={len(err):<4} MAE={err.mean():5.1f} kg   error={(err / actual).mean() * 100:4.1f}%")

def bootstrap_diff(test, col_a, col_b, n_boot=2000, seed=0):
    """95% interval for mean(|error of a|) - mean(|error of b|).
    Positive means `a` is worse than `b`. Resamples whole WEEKS, not single sets,
    because sets from the same week are correlated and would make the interval too narrow."""
    rng = np.random.default_rng(seed)
    d = (test[col_a] - test["weight_kgs"]).abs() - (test[col_b] - test["weight_kgs"]).abs()
    by_week = d.groupby(test["week_index"]).agg(["sum", "count"])   # per-week total difference and set count
    sums, counts = by_week["sum"].to_numpy(), by_week["count"].to_numpy()
    n = len(sums)
    means = []
    for _ in range(n_boot):
        pick = rng.integers(0, n, n)                                # draw n weeks, with replacement
        means.append(sums[pick].sum() / counts[pick].sum())         # mean difference over the drawn weeks
    lo, hi = np.percentile(means, [2.5, 97.5])
    return d.mean(), lo, hi


if __name__ == "__main__":
    df = load_sets("data/jon_sets_v2.csv")
    df = add_recent_strength(df)
    df = add_baselines(df)
    df = df.dropna(subset=["recent_e1rm"])        # no earlier anchor sets = nothing to predict from

    train, test = split_by_time(df)
    models = fit_corrections(train)
    test = test.copy()
    test["pred_model"] = predict_model(test, models)

    print(f"train rows: {len(train)} | test rows: {len(test)}")

    print("\nAll test rows (formula vs model):")
    score("formula", test["weight_kgs"], test["pred_formula"])
    score("model", test["weight_kgs"], test["pred_model"])

    # fair comparison: only rows where all three methods can predict
    common = test.dropna(subset=["pred_last_same"])
    print("\nRows where 'same as last time' also exists:")
    score("last time", common["weight_kgs"], common["pred_last_same"])
    score("formula", common["weight_kgs"], common["pred_formula"])
    score("model", common["weight_kgs"], common["pred_model"])

    print("\nMean absolute error (kg) by block:")
    test["err_formula"] = (test["pred_formula"] - test["weight_kgs"]).abs()
    test["err_model"] = (test["pred_model"] - test["weight_kgs"]).abs()
    print(test.groupby("block")[["err_formula", "err_model"]].mean().round(1))

    print("\nDifference in mean absolute error (positive = first method is worse):")
    for a, b, label in [("pred_formula", "pred_model", "formula minus model"),
                        ("pred_model", "pred_last_same", "model minus last time")]:
        mean, lo, hi = bootstrap_diff(common, a, b)
        print(f"{label}: {mean:+.2f} kg   (95% interval {lo:+.2f} to {hi:+.2f})")