import pandas as pd

ANCHOR_MIN_RPE = 6   # sets at or above this RPE count toward "recent strength"


def load_sets(path: str) -> pd.DataFrame:
    """Loads the export, drops backdown sets, and puts rows in time order."""
    df = pd.read_csv(path)
    df = df[df["prescribed_backoff_pct"].isna()]   # backdowns carry a percentage here
    df = df.sort_values(["week_index", "day_number", "lift", "set_number"])
    return df.reset_index(drop=True)


def add_recent_strength(df, anchor_min_rpe=ANCHOR_MIN_RPE, window=3):
    """recent_e1rm = best anchor-set e1RM over the previous `window` weeks, per lift."""
    anchors = df[df["rpe"] >= anchor_min_rpe]
    best = anchors.groupby(["lift", "week_index"])["e1rm"].max()

    # every (lift, week) pair, so a week with no anchor sets is a NaN row, not a missing one
    full = pd.MultiIndex.from_product(
        [df["lift"].unique(), range(1, df["week_index"].max() + 1)],
        names=["lift", "week_index"],
    )
    best = best.reindex(full)

    # per lift: shift by 1 so a week never sees itself, then take the max over the previous weeks
    best = best.groupby("lift").transform(
        lambda s: s.shift(1).rolling(window, min_periods=1).max()
    )
    return df.merge(best.reset_index(name="recent_e1rm"), on=["lift", "week_index"], how="left")


def add_baselines(df):
    """Adds the two predictions the model has to beat."""
    # 1. The e1RM formula run backwards: weight = e1rm * (37 - (reps + 10 - rpe)) / 36
    eff_reps = df["reps"] + (10 - df["rpe"])
    df["pred_formula"] = df["recent_e1rm"] * (37 - eff_reps) / 36

    # 2. "Same as last time": the load from the most recent EARLIER week with the same lift, reps, and RPE.
    # allow_exact_matches=False restricts it to earlier weeks. Without it, set 2 of a "2x6" row
    # would just copy set 1 and the baseline would look unrealistically good.
    left = df.sort_values("week_index")
    right = (df[["lift", "reps", "rpe", "week_index", "weight_kgs"]]
             .rename(columns={"weight_kgs": "pred_last_same"})
             .sort_values("week_index"))
    merged = pd.merge_asof(left, right, on="week_index",
                           by=["lift", "reps", "rpe"], allow_exact_matches=False)
    return merged.sort_values(["week_index", "day_number", "lift", "set_number"]).reset_index(drop=True)