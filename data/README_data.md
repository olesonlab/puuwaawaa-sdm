# Data

The input data file `pww_sdm_input_data.xlsx` is archived at:

**Zenodo: https://doi.org/10.5281/zenodo.20369405**

A byte-identical copy is committed here, so no download is needed.

## Contents of pww_sdm_input_data.xlsx

| Sheet | Description |
|-------|-------------|
| `paddock_data` | Paddock identifiers, elevation zones, areas (m²), and per-paddock per-alternative costs for Alternatives 1–11. Column E (index 4) is a spacer column preserving the column offsets expected by the optimizer. |
| `native_rareplants` | Native forest cover (%) and T&E plant counts per paddock. Data begin at row 5 (pandas index 4) to preserve row offsets expected by the optimizer. |
| `People` | Expert-elicited community preference base scores for recreationists (cols C–M), hunters (cols P–Z), and ranchers (cols AC–AM) per alternative. Spacer columns at N–O and AA–AB preserve column offsets expected by the optimizer. |
| `flammability` | Baseline Q3 fire probability per paddock (col B) and post-management fire probability per paddock per alternative (cols F–P). Spacer columns at D–E preserve column offsets expected by the optimizer. Data begin at row 5 (pandas index 4). |
| `alternatives` | Reference table describing each of the 11 management alternatives. Not read by the optimizer. |

The workbook also carries four working sheets kept from the elicitation and
cleaning process: `cleaned`, `pivot`, `alt_trans`, and `raw from Clay`. None of
them is read by any script here. They are retained so the committed file matches
the archived Zenodo record exactly.

## The Alt_2 cost column and the roadside fuelbreak

The `Alt_2` column of `paddock_data` is not a per-paddock cost. It is the single
cost of the roadside fuelbreak distributed across paddocks by area at a flat
0.00345277 per m2, so it is exactly proportional to paddock area. Its column
total, 137,677.06, is labelled in the sheet itself: the cell beneath it reads
"note: single cost for roadside fuel break", and 39,874,401 m2 of reserve times
the per-m2 rate reproduces it.

The optimizer therefore ignores that column and charges `ROADSIDE_COST =
137677.06` once when the fuelbreak is built.

Do not use 80,728.08 for this. That figure sits at `paddock_data[44,4]`, in the
separate "Shared borders between paddocks" table, and is the fence cost for the
single border between paddocks 1 and 2 (1090.92 m). It is the first of 46 border
rows whose fence column totals 3,576,698.26. Earlier versions of the model used
it as the shared firebreak cost, which undercharged the fuelbreak by 56,948.98.

## Notes on spacer columns and row offsets

The optimizer (`src/pww_sdm_optimizer.py`) reads data using hardcoded `iloc` indices. The spacer columns and extra header rows in `pww_sdm_input_data.xlsx` are intentional: they preserve the exact column and row offsets the optimizer expects. Do not remove them.

The shared fuelbreak cost (`shared_firebreak_cost = 80,728.08`) is hardcoded in the optimizer and is noted in the `paddock_data` sheet header for reference.

## Data provenance

Paddock boundaries and ecological data derive from DOFAW spatial databases
and the Puʻuwaʻawaʻa management plan (DLNR 2003).

T&E plant counts were compiled by DOFAW from systematic surveys
(Balzotti et al. 2017/2020; DLNR 2003).

Fire probability estimates derive from the spatially explicit fire model
of Trauernicht (2019).

Community preference scores were expert-elicited from DOFAW managers
(co-authors EP, and collaborators) during a 2018 rapid-prototyping workshop.

Costs represent mean estimates from contractor bids and DOFAW records.
