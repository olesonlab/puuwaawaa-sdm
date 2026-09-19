"""
Parity check: pww_sensitivity_analysis must reproduce pww_sdm_optimizer.

pww_sensitivity_analysis.py carries its own copy of the model so that every
elicited input can be swept as a parameter. That copy has drifted before. An
earlier version zeroed the per-paddock cost column for the roadside fuelbreak
without charging it back, which made the fuelbreak free and moved the portfolios
in the two scenarios that spend to the budget ceiling. Nothing was comparing the
two implementations, so it went unnoticed.

This compares them directly at default parameters, in both roadside states.

Usage: python test_parity.py ../../data/pww_sdm_input_data.xlsx
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

import pww_sensitivity_analysis as sens
import pww_sdm_optimizer as opt

TOL = 1e-9


def main(path):
    failures = []

    ind = opt.load_input_data(path)
    d = sens.load_data(path)
    p = sens.default_params()

    if opt.ROADSIDE_COST != sens.ROADSIDE_COST:
        failures.append(
            f"roadside cost differs: optimizer {opt.ROADSIDE_COST:,.2f} "
            f"vs sensitivity {sens.ROADSIDE_COST:,.2f}"
        )

    for roadside_built in (False, True):
        scores_o, opt_indices, _, _ = opt.prepare_scores(ind, roadside_built)
        scores_s, idx_s, costs_s, _, _ = sens.build_scores(d, p, roadside_built)
        costs_o = ind["costs"][opt_indices, :][:, opt.PADDOCK_ALTS]

        tag = "roadside built" if roadside_built else "roadside not built"

        if list(np.asarray(idx_s).ravel()) != list(opt_indices):
            failures.append(f"{tag}: optimized paddock index sets differ")
            continue

        dc = np.abs(costs_o - costs_s).max()
        print(f"[{tag}] cost matrix        max abs diff = {dc:.12f}")
        if dc > TOL:
            cols = sorted({int(c) for c in np.where(np.abs(costs_o - costs_s) > TOL)[1]})
            failures.append(f"{tag}: cost matrices differ (max {dc:,.4f}), columns {cols}")

        for k in sorted(set(scores_o) & set(scores_s)):
            a, b = np.asarray(scores_o[k]), np.asarray(scores_s[k])
            if a.shape != b.shape:
                failures.append(f"{tag}: score '{k}' shape {a.shape} vs {b.shape}")
                continue
            ds = np.abs(a - b).max()
            print(f"[{tag}] score {k:<14} max abs diff = {ds:.12f}")
            if ds > TOL:
                failures.append(f"{tag}: score matrix '{k}' differs (max {ds:.6g})")

    print()
    if failures:
        for f in failures:
            print("FAIL:", f)
        return 1
    print("PASS: the two implementations agree at default parameters.")
    return 0


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "../../data/pww_sdm_input_data.xlsx"
    sys.exit(main(p))
