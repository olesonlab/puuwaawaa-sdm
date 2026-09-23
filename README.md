# Structured Decision Making at Puʻuwaʻawaʻa Forest Reserve

Code and data for:

> Oleson, K.L.L., Trauernicht, C., Lonsdorf, E., and Parsons, E.W.
> **"Structured Decision Making reveals asymmetric tradeoffs between conservation
> and community objectives at Puʻuwaʻawaʻa Forest Reserve, Hawaiʻi"**
> *Conservation Science and Practice* (CSP2-26-0352, in revision)

A companion paper on normalization methods is at
[github.com/olesonlab/puuwaawaa-normalization](https://github.com/olesonlab/puuwaawaa-normalization).

---

## Overview

An integer program evaluates management alternatives across 22 paddocks at
Puʻuwaʻawaʻa Forest Reserve under seven weighting scenarios and five
budget levels ($5M to $60M). Scores are normalized within each paddock, which
keeps spatial priority separate from action effectiveness. The companion paper
explains why that choice matters.

The roadside fuelbreak is a single landscape decision rather than a paddock-level
alternative. It is built once for the reserve or not at all, charged once at
$137,677.06, and when built it lowers fire probability in every paddock. Paddocks
choose among the other ten alternatives. Every scenario and budget is solved
twice, with and without it, and the better solution is kept. It is built at $5M
in every scenario and at $10M in six of seven, and not at $20M and above.

Conservation outcomes are budget-constrained across the range tested; community
objectives largely are not. Rancher and conservation interests align on
Alternative 1, fencing combined with fuelbreaks, which is the modal action under
Rancher-Conservation at $20M in 18 of 21 optimized paddocks. The exchange rate
between rancher gains and T&E plant losses differs sharply across scenarios;
`results/table3.csv` gives the computed ratios. Alternatives 8 and 9 are never
selected at any budget or weighting.

---

## Repository structure

```
puuwaawaa-sdm/
├── src/
│   ├── pww_sdm_optimizer.py   # Integer program (PuLP/CBC)
│   ├── figures.py             # Figures 3, 4, 5 and S1, S2
│   ├── figure1_composite.py   # Figure 1 (map and photographs; inputs not included)
│   ├── generate_tables.py     # Table 1 and Tables S1, S3
│   └── sensitivity/
│       ├── pww_sensitivity_analysis.py   # Figures S3-S9, Tables S2, S4-S7
│       └── test_parity.py                # Guards the two model copies
├── data/
│   ├── pww_sdm_input_data.xlsx
│   └── README_data.md
├── results/                   # Optimizer output and paper tables
├── requirements.txt
└── README.md
```

---

## Setup

```bash
git clone https://github.com/olesonlab/puuwaawaa-sdm.git
cd puuwaawaa-sdm
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## Usage

Run the optimizer:

```bash
python src/pww_sdm_optimizer.py data/pww_sdm_input_data.xlsx results/
```

It writes `sdm_results_summary.csv` (one row per scenario and budget, with a
`roadside_built` column),
`sdm_results_paddock_detail.csv` (one row per scenario, budget, and paddock),
and `sdm_scenario_definitions.csv` to `results/`. Those three files are already
committed, so the figures and tables reproduce without re-solving.

Figures and tables:

```bash
cp data/pww_sdm_input_data.xlsx results/
python src/figures.py         --data-dir results --out-dir figures
python src/generate_tables.py --data-dir results --out-dir results
```

`generate_tables.py` reads costs from the `paddock_data` sheet, so it needs the
workbook in the same directory as the result CSVs.

Figure 2, the objectives hierarchy, was drawn by hand and has no script. The
normalization comparison in Appendix S1 (Figures S10 and S11, Tables S8 to S10)
is produced in the
[puuwaawaa-normalization](https://github.com/olesonlab/puuwaawaa-normalization)
repository.

| Paper item | Script | Output |
| --- | --- | --- |
| Figure 1 | `src/figure1_composite.py` | `Figure_1_map_photos` |
| Figures 3 to 5, S1, S2 | `src/figures.py` | `Figure_3_asymmetry` and so on |
| Table 1 | `src/generate_tables.py` | `results/table1.csv` |
| Table S1 | `src/generate_tables.py` | `results/tableS1_scenario_weights.csv` |
| Table S3 | `src/generate_tables.py` | `results/tableS3_efficiency_20M.csv` |
| Figures S3 to S9, Tables S2, S4 to S7 | `src/sensitivity/pww_sensitivity_analysis.py` | see `src/sensitivity/README.md` |

Sensitivity, fire-feedback and landscape-action analyses live in
`src/sensitivity/`. See `src/sensitivity/README.md` for the stages, runtimes and
outputs. That directory keeps a second copy of the model so every elicited input
can be swept; `test_parity.py` checks the two copies still agree and should be
run after changing either.

---

## Data

`data/pww_sdm_input_data.xlsx` holds expert-elicited consequence scores,
paddock-level spatial data, fire probability estimates, and cost estimates
developed during a 2018 rapid-prototyping workshop with DOFAW managers. See
`data/README_data.md` for sheet-by-sheet metadata and provenance.

Archived at **https://doi.org/10.5281/zenodo.20369405** (CC BY 4.0). The
committed copy is byte-identical to the archived one.

---

## Dependencies

Python 3.9 or later, with numpy, pandas, matplotlib, and pulp. PuLP installs the
CBC solver on most platforms. `requirements.txt` pins versions.

---

## Citation

See `CITATION.cff`, or:

```bibtex
@article{oleson_puuwaawaa_sdm,
  title   = {Structured Decision Making reveals asymmetric tradeoffs between
             conservation and community objectives at {Puʻuwaʻawaʻa} Forest
             Reserve, {Hawaiʻi}},
  author  = {Oleson, Kirsten L. L. and Trauernicht, Clay and
             Lonsdorf, Eric and Parsons, Elliott W.},
  journal = {Conservation Science and Practice},
  note    = {In revision}
}
```

---

## License

Code: MIT License (see `LICENSE`). Data: CC BY 4.0.

---

## Contact

Kirsten Oleson, koleson@hawaii.edu
Department of Natural Resources and Environmental Management
University of Hawaiʻi at Mānoa
