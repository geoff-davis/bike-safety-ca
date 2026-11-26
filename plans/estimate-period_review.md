# Review: estimate-period

## Current state

- Status: complete (round 2 accepted)
- Next action: none
- Base commit: `4feaa31`; snapshot: `/tmp/bsc-review/estimate-period-r2/`
- Open findings: none
- Decisions needed from the user: none

## Loop

- Loop ID and round: `estimate-period-1`, round 2 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-model-review`
- Reviewer: `bsc-reviewer` (Codex), pane `wF:p2`
- Authorized scope: review requests and replies only
- Expires (UTC): `2026-11-24T04:14:45Z`

## Handoff, round 1

- Tier: Standard
- Intended behavior and acceptance criteria. Two separate things.
  1. Wording of the model's estimate on the map and the one-page list. The number shown (`expected_bike_crashes`) is the model's estimate of recorded bike crashes over the whole period the ranking was built from. It is not per year and not a forecast. The values are unchanged; only what the reader is told changes.
     - `report.ranking.why(row, years)` names the years for the recorded counts and the estimate ("Recorded in 2015–2024: ... Model estimate for the same years: about 4.2 bike crashes."). A corner ranked by the blend still gets no estimate. Before, a ranked corner's popup gave no years while an unranked one did.
     - The map's key, circle key, print key and popups say "estimate" and name the period; "the model expects" is gone from the template.
     - The ranking file records the years of the crashes it was built from (`first_year`, `last_year`, the same on every row; from every placed crash, so a child ranking has the same years). `report.ranking.period` reads them and the report uses them for the ranking's wording; a ranking written before this falls back to the crash table's years as before.
  2. Two fixes to the research comparator `model/standard_eb.py`, found while answering the outside reviewer:
     - The Poisson fit supplies starting values only, but its non-convergence was treated as failure of the model. With a road class that has no bike crash the Poisson fit never converges (the coefficient runs to minus infinity) while the NB2 fit does. Now only the NB2 fit must converge, and the starting values must be finite.
     - A regression column that is the same at every site (other than the constant) is left out: on a uniform grid the neighbour-count column is a second constant and made the design singular. This was the cause of an intermittent `LinAlgError` in `test_street_context_enters_the_regression_only_when_streets_are_given`.
- Changed areas and affected producers and consumers: `model/ranking.py` (two new columns in `COLUMNS`), `report/ranking.py`, `report/__main__.py`, `report/movement_map.html` (text only), `model/standard_eb.py`, `docs/guide.md`, tests. Consumers of the ranking CSV: `report.ranking` (reads columns by name) and the tests; nothing reads it by position.
- Pattern inventory: "expects"/"expected" in reader-facing text was searched in `report/`; the remaining uses are the column name `expected_bike_crashes` (kept: renaming it would break existing files) and code comments.
- Verification: `make check` | working tree on 4feaa31 | 685 passed | slow tests deselected | bsc-implementer.
- Expected test values changed, and why:
  - `test_each_corner_says_what_the_model_saw`: the sentence itself is what changed (years named, "estimate" for "expects").
  - `test_street_context_enters_the_regression_only_when_streets_are_given`: its made-up city was a uniform grid, where the neighbour count is constant. It now checks that the constant column is left out there, and checks both columns on a grid where every seventh site keeps one street.
  - `test_a_textbook_model_can_be_the_reference`: with the constant column gone, the made-up city has no spread of rates left for the street-context model (its rates follow its streets exactly), so the NB2 fit rightly finds none and falls back. Every tenth site is given three times its adult crashes so that there is spread to fit. The earlier pass depended on the singular column.
- Condition inventory:

  | Condition | Test or probe | Caught / survived / not exercised | Note |
  | --- | --- | --- | --- |
  | ranked popup names the years | `test_each_corner_says_what_the_model_saw` | caught | |
  | blend: no estimate invented | same test | caught | |
  | no years known | same test ("the years used") | caught | |
  | ranking records its years; crash before first year not counted | `test_a_small_town_is_ranked_as_worked_out_by_hand` | caught | 2016 to 2023 |
  | old ranking file without the columns | `test_the_period_is_the_rankings_own_where_it_records_one` | caught | |
  | columns present but empty | same test | caught | |
  | template wording | `test_the_risk_key_names_the_period_and_does_not_promise_a_forecast` | caught | text match only; the page is not rendered |
  | Poisson start not converged, NB2 converged | `test_a_road_class_with_no_bike_crash_does_not_stop_the_fit` | caught | |
  | constant context column | `test_street_context_enters_...` | caught | |
  | Poisson start not finite | none | not exercised | raises RuntimeError, which `rank_standard` turns into the count fallback |

- Settled decisions (do not re-report): the column stays named `expected_bike_crashes`; the period is given as first to last year of placed crashes, the last of which may be a part year; no annual or forecast figure is added.
- Known limitations and out of scope: a road class with no bike crash gets an estimate near zero at all its sites (the fitted coefficient is very negative). That is the model as specified; it is noted, not changed.

## Review, round 1 — estimate-period-1

Verdict: **changes required** (round 1).

- **EP-001 — confirmed dimension-contract failure, medium:** `model/standard_eb.py`, new constant-column filtering in `fit_standard_eb()`, and its consumer `model/street_effects.py`, `fit_street_effects()` design/initialization. The plain fit now returns coefficients for a reduced design, but the street-effects fit independently constructs its unfiltered design and initializes its regression from those reduced coefficients. Concrete case: every site's car count is the same (including all zero), with enough varying bike counts for the plain model to fit. The new filter removes the constant log-car predictor. `fit_street_effects()` still includes it in `both`/`fixed`, so `state['at']` has one fewer entry than `both` has columns; `_modes()` fails at `both @ at`, and the rank wrapper falls back instead of fitting. With two original fixed columns and three streets, the matrix has five columns but the initial vector has four entries. Share the same retained-column design between the models, or align the street-effects columns to the plain coefficient index before constructing `both`, `fixed` and the start. Add a constant-car regression exercising both plain and street-effects fits, not only the standalone standard fit.

Other review: the period metadata is derived from the placed-crash years and propagated consistently to ranking popups, circles and the one-pager; legacy/missing metadata retains the specified fallback. The wording distinguishes the whole-period estimate from an annual rate or forecast. No separate correctness finding in the period changes or the finite-Poisson-start/NB2-convergence rule.

Validation: executed the exact new constant-column filter with controlled column stand-ins; the constant log-car predictor was removed while the intercept remained. Executed the exact street-effects start construction and `_modes()` with a dimension-checking matrix stand-in: the five-column/four-entry case failed at the matrix product. This verifies the producer/consumer shape mismatch; it is not an end-to-end numerical optimizer reproduction. Executed the exact `period()` function with metadata, legacy missing columns, missing values and an empty table; all returned the intended period/fallback. Reviewed the staged text, period wiring, tests and the unchanged street-effects consumer. Full pandas/numpy/SciPy/statsmodels integration and `make check` were not rerun; the handoff reports 685 passing tests. No protected files or records were opened.

Finding ledger: EP-001 open. Test the finding before changing staged files, then request round 2 with a fresh snapshot. Implementer releases the reviewer lock. Review does not authorize commit, push or merge.

## Handoff, round 2

- EP-001: confirmed before fixing. The new test `test_street_effects_fit_when_every_site_has_the_same_car_count` failed with `matmul: dimension mismatch (n,k=63),(k=62)`. Fix: the filter moved into `standard_eb.design` itself (`_varying`), so `fit_standard_eb` and `fit_street_effects` build the same columns; the street-context columns are filtered by the same helper before they are joined. The test now passes.
- Verification: `make check` | working tree on 4feaa31 | 686 passed | slow tests deselected | bsc-implementer.
- Docs under `docs/` also changed since round 1 (exempt paths).

## Review, round 2 — estimate-period-1

Verdict: **accepted** (round 2). No new correctness findings.

**EP-001 — closed, fixed:** constant-column filtering now lives in the shared `design()` function, so the ordinary fit's coefficient vector and the street-effects matrix have the same fixed columns. Additional context columns are independently filtered before concatenation, preserving the ordinary design. The new constant-car street-effects regression was observed failing before the fix and now passes according to the handoff.

Validation: executed the exact `design()`/`_varying()` functions with minimal column/numeric stand-ins and the exact street-effects start construction. Constant nonzero car counts and all-zero car counts retained only the intercept; varying car counts retained the car predictor; in all three cases the shared design width plus street count matched the start length. A constant neighbour column was dropped while a varying context-rate column remained. Reviewed the updated source, regression and previously reviewed period propagation; exempt documentation changes were not treated as code findings. These are isolated checks, not a full pandas/numpy/SciPy/statsmodels fit. Full `make check` was not rerun; the handoff reports 686 passing tests. No protected files or records were opened.

Final ledger: EP-001 closed; no open findings. Loop estimate-period-1 complete. Implementer releases the reviewer lock. Acceptance does not authorize commit, push or merge.
