import os
import matplotlib
matplotlib.use("Agg")                       # draw to files only, no pop-up window
import matplotlib.pyplot as plt

from prepare import load_sets
from walkforward import build_dataset, walk_forward

DATA = "data/client_sets_v2.csv"            # use your actual filename
OUT = "charts"


def chart_loads(df):
    """Heaviest logged working-set load per week, one line per lift (backdowns already excluded)."""
    weekly = df.groupby(["week_index", "lift"])["weight_kgs"].max().unstack()   # rows = weeks, columns = lifts
    fig, ax = plt.subplots(figsize=(9, 4))
    weekly.plot(ax=ax, marker="o", markersize=3)
    ax.set_title("Client: heaviest logged load per week")
    ax.set_xlabel("Week")
    ax.set_ylabel("Load (kg)")
    fig.tight_layout()
    fig.savefig(f"{OUT}/loads_by_week.png", dpi=150)


def chart_error_by_week(res):
    """Mean absolute error per week for the formula and the model, over the walk-forward weeks."""
    res = res.copy()
    res["err_formula"] = (res["pred_formula"] - res["weight_kgs"]).abs()
    res["err_model"] = (res["pred_model"] - res["weight_kgs"]).abs()
    weekly = res.groupby("week_index")[["err_formula", "err_model"]].mean()

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(weekly.index, weekly["err_formula"], label="Formula", color="tab:gray")
    ax.plot(weekly.index, weekly["err_model"], label="Model", color="tab:blue")
    for w in res.loc[res["block"] == 4, "week_index"].unique():   # mark the week scored right after the break
        ax.axvline(w, linestyle="--", color="tab:red", alpha=0.5)
        ax.text(w, weekly.max().max(), " block 4", color="tab:red", va="top")
    ax.set_title("Client: mean absolute error per week (walk-forward)")
    ax.set_xlabel("Week")
    ax.set_ylabel("Error (kg)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(f"{OUT}/error_by_week.png", dpi=150)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    chart_loads(load_sets(DATA))
    chart_error_by_week(walk_forward(build_dataset(DATA)))
    print("saved to", OUT)