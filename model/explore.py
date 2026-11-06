import pandas as pd

df = pd.read_csv("data/jon_sets_v2.csv")
gap = (df["rpe"] - df["prescribed_rpe"]).dropna()
print(len(gap), "sets have both RPEs")
print(gap.round(1).value_counts().sort_index())   # how often actual differs from prescribed