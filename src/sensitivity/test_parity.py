"""
Parity check: pww_core must reproduce pww_sdm_optimizer at default parameters.

pww_core.py re-implements the model of src/pww_sdm_optimizer.py with every
elicited input exposed as a parameter. The two are meant to be the same model.
They silently diverged once: pww_core zeroed the per-paddock cost of
Alternative 2, which made roadside fuelbreaks free, and the Balanced and
Community Priority scenarios, both of which press against the budget ceiling,
drifted to portfolios the real budget could not afford. load() asserted the
community score matrices against the People sheet, but nothing checked costs.

Run this after any change to either model.

Usage: python test_parity.py ../../data/pww_sdm_input_data.xlsx
"""
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pww_core as core
import pww_sdm_optimizer as opt

TOL = 1e-6


def main(path):
    ind = opt.load_input_data(path)
    scores_o, opt_indices = opt.prepare_scores(ind)
    costs_o = ind["costs"][opt_indices, :]

    d = core.load(path)
    p = core.default_params()
    scores_c, idx_c, costs_c, _, _ = core.build_scores(d, p)

    failures = []

    dc = np.abs(costs_o - costs_c).max()
    print(f"cost matrix        max abs diff = {dc:.10f}")
    if dc > TOL:
        rows, cols = np.where(np.abs(costs_o - costs_c) > TOL)
        failures.append(
            f"cost matrices differ (max {dc:,.2f}); "
            f"alternatives {sorted({int(c) + 1 for c in cols})}"
        )

    for k in sorted(set(scores_o) & set(scores_c)):
        ds = np.abs(scores_o[k] - scores_c[k]).max()
        print(f"score {k:<14} max abs diff = {ds:.10f}")
        if ds > TOL:
            failures.append(f"score matrix '{k}' differs (max {ds:.6g})")

    if list(np.asarray(idx_c).ravel()) != list(opt_indices):
        failures.append("optimized paddock index sets differ")

    if ind["shared_firebreak_cost"] != core.SHARED_FIREBREAK_COST:
        failures.append("shared firebreak cost differs")

    print()
    if failures:
        for f in failures:
            print("FAIL:", f)
        return 1
    print("PASS: pww_core matches pww_sdm_optimizer at default parameters.")
    return 0


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "../../data/pww_sdm_input_data.xlsx"
    sys.exit(main(path))
