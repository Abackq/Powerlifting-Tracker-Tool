import pandas as pd
from prepare import load_sets, add_recent_strength, add_baselines
from evaluate import fit_corrections, bootstrap_diff, score

WARMUP_WEEKS = 10   # weeks 1-10 are never scored; they only provide training history


def build_dataset(path):
    """Same preparation as v1, plus a 'novel' flag: True when a set's (lift, reps, rpe)
    combination has never appeared in an earlier week (every set in its first week counts)."""
    df = load_sets(path)
    first_week = df.groupby(["lift", "reps", "rpe"])["week_index"].transform("min")
    df["novel"] = df["week_index"] == first_week
    df = add_recent_strength(df)
    df = add_baselines(df)
    return df.dropna(subset=["recent_e1rm"]).reset_index(drop=True)


def walk_forward(df, warmup=WARMUP_WEEKS):
    """For each week after the warm-up, fit on ALL earlier weeks (expanding window), then predict that week."""
    scored = []
    for week in sorted(df["week_index"].unique()):
        if week <= warmup:
            continue
        train = df[df["week_index"] < week]          # strictly earlier weeks only
        test = df[df["week_index"] == week].copy()
        models = fit_corrections(train)              # one small linear model per lift
        test["pred_model"] = test["pred_formula"]    # fallback if a lift had no training rows
        for lift, g in test.groupby("lift"):
            if lift in models:
                test.loc[g.index, "pred_model"] = models[lift].predict(g[["pred_formula", "rpe"]])
        scored.append(test)
    return pd.concat(scored)


if __name__ == "__main__":
    df = build_dataset("data/client_sets_v2.csv")    # use your actual filename
    res = walk_forward(df)

    n_novel = int(res["novel"].sum())
    print(f"{res['week_index'].nunique()} weeks scored | {len(res)} sets | "
          f"{n_novel} novel (expect 39) | {len(res) - n_novel} repeats")

    print("\nAll scored sets:")
    score("formula", res["weight_kgs"], res["pred_formula"])
    score("model", res["weight_kgs"], res["pred_model"])

    rep = res[~res["novel"] & res["pred_last_same"].notna()]
    print("\nRepeat sets (last time can predict these):")
    score("last time", rep["weight_kgs"], rep["pred_last_same"])
    score("formula", rep["weight_kgs"], rep["pred_formula"])
    score("model", rep["weight_kgs"], rep["pred_model"])

    nov = res[res["novel"]]
    print("\nNovel sets (exploratory: small sample, no 'last time' exists by definition):")
    score("formula", nov["weight_kgs"], nov["pred_formula"])
    score("model", nov["weight_kgs"], nov["pred_model"])

    print("\n95% intervals, weeks resampled (positive = first method is worse):")
    for label, data, a, b in [("formula - model, all sets", res, "pred_formula", "pred_model"),
                              ("model - last time, repeats", rep, "pred_model", "pred_last_same"),
                              ("formula - model, novel sets", nov, "pred_formula", "pred_model")]:
        mean, lo, hi = bootstrap_diff(data, a, b)
        print(f"{label}: {mean:+.2f} kg  ({lo:+.2f} to {hi:+.2f})")

    res["err_formula"] = (res["pred_formula"] - res["weight_kgs"]).abs()
    res["err_model"] = (res["pred_model"] - res["weight_kgs"]).abs()
    print("\nMean absolute error (kg) by block:")
    print(res.groupby("block")[["err_formula", "err_model"]].mean().round(1))

        # Block 4 check. Signed error = prediction minus actual (positive = predicted too heavy).
    res["signed_formula"] = res["pred_formula"] - res["weight_kgs"]
    res["signed_model"] = res["pred_model"] - res["weight_kgs"]
    b4 = res[res["block"] == 4]
    print("\nBlock 4:", len(b4), "sets, weeks", sorted(b4["week_index"].unique()))
    print(b4.groupby(["week_index", "lift"])[["signed_formula", "signed_model"]].mean().round(1))

    # Robustness: the headline comparison without block 4
    rest = res[res["block"] != 4]
    print(f"\nWithout block 4 ({len(rest)} sets):")
    score("formula", rest["weight_kgs"], rest["pred_formula"])
    score("model", rest["weight_kgs"], rest["pred_model"])
    mean, lo, hi = bootstrap_diff(rest, "pred_formula", "pred_model")
    print(f"formula - model: {mean:+.2f} kg  ({lo:+.2f} to {hi:+.2f})")

    # Early vs late: the same walk-forward predictions, scored separately on each half of the scored weeks.
    weeks = sorted(res["week_index"].unique())
    split_week = weeks[len(weeks) // 2]            # first week of the late half (the middle scored week)
    print("\nEarly vs late half:")
    for label, part in [("early", res[res["week_index"] < split_week]),
                        ("late", res[res["week_index"] >= split_week])]:
        mean, lo, hi = bootstrap_diff(part, "pred_formula", "pred_model")
        print(f"{label}: weeks {part['week_index'].min()}-{part['week_index'].max()}, {len(part)} sets | "
              f"formula - model {mean:+.2f} kg ({lo:+.2f} to {hi:+.2f})")
        score(f"  formula ({label})", part["weight_kgs"], part["pred_formula"])
        score(f"  model ({label})", part["weight_kgs"], part["pred_model"])