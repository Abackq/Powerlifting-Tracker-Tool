# Load prediction model (v1)

**Question:** given a lift, a rep count, and a target RPE, how heavy will the set be?
The use case is a coach picking a load for a prescribed set.

> All results come from **one client's** training data (about 53 weeks, three comp lifts).
> They describe that client only and are not findings about lifters in general.

## Setup

- **Data:** a CSV export of one client's comp-lift sets, with a week index that runs across all blocks.
  Backdown sets are excluded. The export contains client data, so it is gitignored (`data/`).
- **Recent strength:** for each lift and week, the best e1RM from sets at RPE 6 or above
  over the previous 3 weeks. Earlier weeks only, so a week never sees itself.
- **Split:** time-ordered. The first 70% of weeks train the model and the last 30% test it
  (453 and 191 sets).

## Methods compared

| Method | What it does |
| --- | --- |
| Formula | The e1RM formula (Brzycki with an RPE-to-reps-in-reserve adjustment) run backwards from recent strength |
| Model | The formula plus a small per-lift linear correction on RPE |
| Last time | The load used in the most recent earlier week with the same lift, reps, and RPE |

## Results (test weeks, mean absolute error)

| Method | Error (kg) | Error (%) |
| --- | --- | --- |
| Formula | 5.2 | 3.9% |
| Model | 4.9 | 3.4% |
| Last time (187 comparable sets) | 3.9 | 2.8% |

95% intervals, resampling whole weeks:
- Formula minus model: +0.30 kg (-0.33 to +0.93). The two cannot be told apart.
- Model minus last time: +0.90 kg (+0.18 to +1.63). Last time predicted better.

For this client, the load he used last time at the same lift, reps, and RPE was the best predictor,
and the learned correction adds little over the formula.

## Limits

- One lifter, about 15 test weeks.
- Most sets sit at RPE 5-6, so the model has little to learn from at RPE 8-9.
- `reps` is the prescribed count, not necessarily what was performed.
- The e1RM formula overstates strength at low RPE.
- Bodyweight changes are not modeled.

## Run it

```powershell
pip install -r requirements.txt
python evaluate.py
```

Needs `data/<export>.csv` (not included).