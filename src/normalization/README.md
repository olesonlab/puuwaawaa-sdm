# Normalization comparison (Appendix S1)

The main analysis scales the two conservation objectives within each paddock and the three community objectives globally. Appendix S1 documents how portfolios change under two other specifications of the conservation scores, and when the conservation and community scalings are crossed. These are alternative specifications of conservation value, not a correct method and incorrect ones.

- **Within-unit** (main analysis): action effectiveness rescaled to [0, 1] within each paddock; T&E scores are 0 where no T&E plants are recorded.
- **Global linear**: action effectiveness times the paddock's T&E count (or native cover), min-max rescaled over all 21 optimized paddocks and 10 paddock-level alternatives.
- **Vector**: the same products divided by the Euclidean norm of the whole matrix.

"Global" here means the minimum and maximum are taken over the options in the model, not over a range set outside it.

## Files

| File | What it does | Output |
| --- | --- | --- |
| `norm_model.py` | Imports the data loader, scoring, scenarios and integer program from `src/pww_sdm_optimizer.py` and adds vector scaling and crossed scaling | none (module) |
| `normalization_runs.py` | Score spreads; portfolios for seven scenarios at five budgets under each conservation scaling; $20M exchange ratios for four crossed pairings. CBC via PuLP 2.9.0, about 15 seconds | `appendix_score_spread.csv`, `appendix_normalization_portfolios.csv`, `normalization_symmetry.csv` |
| `appendix_s1_figures.py` | Reads those CSVs, no solver | `figures/Figure_S10_score_spread`, `figures/Figure_S11_conservation_priority_by_normalization` (PDF and 600 dpi PNG), `figures/TableS8_score_spread.csv`, `figures/TableS9_portfolios_20M_by_normalization.csv`, `figures/TableS10_crossed_normalization.csv` |

```bash
python src/normalization/normalization_runs.py
python src/normalization/appendix_s1_figures.py
```

The three run CSVs are committed, so the figures and tables reproduce without the solver.

With within-unit conservation scores and global community scores, `norm_model.prepare_scores_method` returns the same scores as `pww_sdm_optimizer.prepare_scores`, and the first row of Table S10 reproduces the main analysis: asymmetry ratio 1.7528, and 3.3132, 0.5851 and 0.4042 rancher or hunter points per T&E point lost for S6, S5 and S7.

## Provenance

This code was first written and archived in the methods repository [olesonlab/puuwaawaa-normalization](https://github.com/olesonlab/puuwaawaa-normalization) (`src/normalization_comparison.py`, parts 3 and 4, and `src/csp_appendix_figures.py`, at commit 1974e00). It was moved here on 2026-11-08 so the CSP paper's code is self-contained. Only the parts behind Appendix S1 were moved; the simulated landscapes, the empirical comparison table and the tradeoff frontier stay in the methods repository. The rerun here reproduces that repository's committed CSVs (portfolio choices identical, total costs within $2e-9), Tables S8 to S10 byte for byte, and Figures S10 and S11 pixel for pixel.
