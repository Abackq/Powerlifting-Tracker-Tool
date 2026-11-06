from prepare import load_sets, add_recent_strength

WARMUP_WEEKS = 10   # weeks 1-10 are never scored; they only provide training history

df = load_sets("data/client_sets_v2.csv")   # use your actual filename

# A set is "novel" if its (lift, reps, rpe) combination hasn't appeared in any EARLIER week.
# This runs on the full data BEFORE any filtering, so a combination's true first week isn't misjudged.
# transform("min") gives, for every row, the first week its combination ever appears.
first_week = df.groupby(["lift", "reps", "rpe"])["week_index"].transform("min")
df["novel"] = df["week_index"] == first_week

df = add_recent_strength(df)
df = df.dropna(subset=["recent_e1rm"])        # same filter as v1: need an earlier anchor set to predict from

scored = df[df["week_index"] > WARMUP_WEEKS]
print(len(scored), "sets to score:", scored["novel"].sum(), "novel,", (~scored["novel"]).sum(), "repeats")
print(scored.groupby("lift")["novel"].agg(["sum", "count"]))    # novel vs total, per lift
print(scored[scored["novel"]].groupby("block").size())          # which blocks the novel sets come from