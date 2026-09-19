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

An integer program evaluates 11 management alternatives across 22 paddocks at
Puʻuwaʻawaʻa Forest Reserve under seven stakeholder weighting scenarios and five
budget levels ($5M to $60M). Scores are normalized within each paddock, which
keeps spatial priority separate from action effectiveness. The companion paper
explains why that choice matters.

Conservation outcomes are budget-constrained across the range tested; community
objectives largely are not. Scenarios converge below roughly $10M and diverge
above it. Rancher and conservation interests align on Alternative 1, fencing
combined with fuelbreaks. The exchange rate between rancher gains and T&E plant
losses differs sharply across scenarios; `results/table3.csv` gives the
computed ratios.

---

## Repository structure

```
puuwaawaa-sdm/
├── src/
│   ├── pww_sdm_optimizer.py   # Integer program (PuLP/CBC)
│   ├── figures.py             # Figures 2, 3, 4, S2, S3
│   ├── generate_tables.py     # Tables 1, 2, 3
│   └── sensitivity/           # Robustness and fire-feedback analyses
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

It writes `sdm_results_summary.csv` (one row per scenario and budget),
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

Sensitivity and fire-feedback analyses live in `src/sensitivity/`. See
`src/sensitivity/README.md` for what each script does, how long it runs, and
what it writes.

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
