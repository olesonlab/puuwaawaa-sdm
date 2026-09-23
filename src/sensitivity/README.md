# Sensitivity analysis

Code for the sensitivity analyses added to *Structured Decision Making reveals
asymmetric tradeoffs between conservation and community objectives at
Puʻuwaʻawaʻa Forest Reserve, Hawaiʻi* during revision (Conservation Science and
Practice, CSP2-26-0352).

Reviewer 2 asked how robust the results are to uncertainty in the elicited
values of Table 1. Reviewer 1 asked why only fuelbreaks change fire risk, and
specifically whether removing grazers should raise it.

## Files

| File | What it does |
| --- | --- |
| `pww_sensitivity_analysis.py` | The whole analysis. It re-expresses the model of `src/pww_sdm_optimizer.py` with every elicited or assumed input as an explicit parameter, then runs one-at-a-time perturbation of each input, Monte Carlo perturbation jointly and by source, continuous sweeps of the objective weights, sweeps of two fire feedbacks the consequence table omits, a sweep of the weight on fire risk treated as a fundamental objective on an absolute scale, and a sweep of a taper in the roadside fuelbreak benefit with distance from the highway. |
| `test_parity.py` | Compares this file's copy of the model against `src/pww_sdm_optimizer.py` at default parameters, in both roadside states. Run it after touching either one. |

No dependencies beyond those in `requirements.txt`.

## Running it

```bash
python pww_sensitivity_analysis.py ../../data/pww_sdm_input_data.xlsx out --draws 500
```

Stages run separately with `--stages sensitivity`, `--stages feedbacks`,
`--stages landscape`, `--stages decay`, or `--stages figures`. The figure stage reads the CSVs, so
figures can be redone without reoptimizing. Timing scales with cores: `--draws
500` is roughly 20 to 30 minutes on 8 cores. `--draws 20` confirms the pipeline
works, though the percentages mean nothing at that size.

Outputs are `sa_baseline_metrics.csv`, `sa_oat.csv`, `sa_montecarlo.csv`,
`sa_weight_sweep.csv`, `ff_sweeps.csv`, `ff_grid.csv`, `ff_montecarlo.csv`,
`la_fire_objective.csv`, `rd_decay_sweep.csv`, `rd_decay_thresholds.csv`,
Figures S3 to S9, and Tables S2 and S4 to S7, numbered as in Appendix S1.

The second and third findings in Table S2 (Community Priority is never the
cheaper route to rancher score, and hunter alignment is weaker than rancher
alignment) count a draw as holding when Rancher-Conservation gives up no T&E
score, since its exchange ratio is then undefined and Community Priority cannot
be cheaper. An earlier version counted those draws as failures.

## Why parity is checked

`pww_sensitivity_analysis.py` keeps its own copy of the model because the
parametrized version needs every Table 1 value as an argument. That copy has
drifted before. An earlier version zeroed the per-paddock cost column for the
roadside fuelbreak without charging the landscape cost back, which made the
fuelbreak free and moved the portfolios in the two scenarios that spend to the
budget ceiling. Nothing compared the two implementations, so it went unnoticed
until the reported exchange ratios stopped matching the optimizer's. Run
`test_parity.py` after any change to either file.

## Baseline values

At default parameters: asymmetry ratio 1.75, S6 3.31 rancher points per T&E
point lost, S5 0.59, S7 0.40 hunter points per T&E point lost, and 18 paddocks
on Alternative 1 under Rancher-Conservation at $20M. Alternatives 8 and 9 are
never selected. The roadside fuelbreak is built at $5M in every scenario and at
$10M in six of seven, and not at $20M and above.
