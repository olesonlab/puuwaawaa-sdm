# Sensitivity analysis

Code for the sensitivity analyses added to *Structured Decision Making reveals
asymmetric tradeoffs between conservation and community objectives at
Puʻuwaʻawaʻa Forest Reserve, Hawaiʻi* during revision (Conservation Science and
Practice, CSP2-26-0352).

Two reviewer requests drive this directory. Reviewer 2 asked how robust the
results are to uncertainty in the elicited values of Table 1. Reviewer 1 asked
why only fuelbreaks change fire risk, and specifically whether removing grazers
should raise it.

## Files

| File | What it does |
| --- | --- |
| `pww_core.py` | The optimizer of `src/pww_sdm_optimizer.py` rewritten so that every elicited or assumed input is an explicit parameter. Same data extraction, scoring, within-unit normalization, and integer program. `load()` asserts that the community score matrices it reconstructs from base scores and elevation multipliers equal the values in the People sheet, so the parametrization is verified against the data on every run. |
| `pww_sensitivity.py` | One-at-a-time perturbations, Monte Carlo over the elicited inputs, and the weight sweeps. |
| `pww_fire_feedback.py` | The two fire feedbacks the consequence table omitted, swept one at a time and on a 2-D grid, plus a Monte Carlo that adds them to the joint perturbation. |
| `pww_sensitivity_figures.py` | Figures S4 to S7 and Tables S2 and S3 from the CSVs. |
| `pww_fire_feedback_figures.py` | Figure S8 and Table S4. |

No dependencies beyond those already in `requirements.txt` (numpy, pandas,
matplotlib, pulp).

## Running

From the repository root, with the input workbook in `data/`:

```bash
# 1. Sensitivity: baseline, weight sweeps, one-at-a-time, Monte Carlo
python src/sensitivity/pww_sensitivity.py data/pww_sdm_input_data.xlsx results/sensitivity 2000

# 2. Fire feedbacks: sweeps, 2-D grid, Monte Carlo
python src/sensitivity/pww_fire_feedback.py data/pww_sdm_input_data.xlsx results/sensitivity 2000

# 3. Figures and supplementary tables
python src/sensitivity/pww_sensitivity_figures.py results/sensitivity
python src/sensitivity/pww_fire_feedback_figures.py results/sensitivity
```

The last argument of steps 1 and 2 is the number of Monte Carlo draws, and the
published figures use 2000. Note that step 1 runs five designs sized `n/2`,
`n/2`, `n/2`, `n`, and `n/2`, so `n = 2000` is 6000 draws in total.

Both scripts parallelize across cores with `multiprocessing.Pool`. Measured on
two cores: about 1.5 seconds of wall time per draw, plus fixed costs of roughly
110 seconds for the one-at-a-time sweep in step 1 and 100 seconds for the sweeps
and 2-D grid in step 2. That puts `n = 2000` at about two and a half hours for
step 1 and one hour for step 2, falling roughly linearly with core count. A
draw count of 4 finishes in about two minutes and is enough to check that the
pipeline works end to end, though the robustness percentages mean nothing at
that size.

## Outputs

`pww_sensitivity.py` writes:

- `sa_baseline_metrics.csv` — every headline metric at the baseline parameters
- `sa_weight_sweep.csv` — continuous ecological weight from 0 to 1 at all five budgets, plus an ecological weight × rancher share grid at $20M
- `sa_oat.csv` — one row per one-at-a-time perturbation
- `sa_montecarlo.csv` — one row per draw, tagged by perturbation source

`pww_fire_feedback.py` writes `ff_sweeps.csv`, `ff_grid.csv`, and
`ff_montecarlo.csv`.

The figure scripts write `FigS4` to `FigS8` as PNG and PDF, and
`TableS2_robustness_summary.csv`, `TableS3_paddock_stability_20M.csv`, and
`TableS4_fire_feedback_summary.csv`.

## What the perturbations cover

**One-at-a-time.** Each of the 11 direct conservation benefit scores and each
community base score moved by ±1 scale point; each elevation-zone multiplier
by ±50%; the fuelbreak effect across 25 to 75% against a baseline of 50%; the
roadside effect across 10 to 30% against 20%; each per-paddock cost by ±30%.
Alternative 11 (no change) is held at zero as the scale anchor, and Alternative
2 carries no per-paddock cost, so neither is perturbed on cost.

**Monte Carlo.** Five designs: each of the three input sources perturbed alone,
all three jointly at ±1, and all three jointly at ±2. Every draw reoptimizes all
35 scenario × budget combinations and records whether each headline finding
still holds.

**Fire feedbacks.** `cattle_penalty` raises post-treatment fire probability
proportionally for the alternatives that remove cattle (4, 5, 6, 9) and for full
restoration (7); `hunter_penalty` raises it for the alternatives that leave a
paddock open to hunters and other users (1, 2, 3, 8, 10, 11). The first is swept
0 to 1.0, the second 0 to 0.5.

## Baseline values

Running `pww_sensitivity.py` reproduces the numbers reported in the paper at the
baseline parameters:

| Metric | Value |
| --- | --- |
| Asymmetry ratio (T&E lost to S5 ÷ T&E gained by S2) | 5.85 |
| S6 rancher points per T&E point lost | 3.26 |
| S5 rancher points per T&E point lost | 0.88 |
| S7 hunter points per T&E point lost | 0.84 |
| Alternative 1 paddocks under S6 at $20M | 15 |

If these differ after a change to `pww_core.py`, the change has altered the
model, not just the parametrization.
