# Review: textbook-models

## Current state

- Status: complete (round 2 accepted)
- Next action: none
- Base commit: `3601532`; snapshot: `/tmp/bsc-review/textbook-models-r2/`
- Open findings: none
- Decisions needed from the user: none

## Loop

- Loop ID and round: `textbook-models-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-model-review`
- Reviewer: `bsc-reviewer` (Codex), pane `wF:p2`
- Authorized scope: review requests and replies only
- Expires (UTC): `2026-11-24T02:21:30Z`

## Handoff, round 1

- Tier: Standard
- Intended behavior and acceptance criteria. Two research challengers to the street model, for comparison only; no ranking, report or default uses them.
  - `model/standard_eb.py`: the textbook model. Counts over `years` are NB2 with mean `years * m`, `log m` = constant + log(1 + car crashes per year) + indicators for the classes of the two main roads (every label but the commonest per column). Fitted with statsmodels `NegativeBinomial` (offset log years). Estimate = `predicted * (k + count) / (k + predicted)`, k = 1/alpha. `rank_standard` falls back to the site's own count under 100 crashes or when the fit fails.
  - `model/street_effects.py`: the same plus a normal effect per named street on the log rate, one membership per street at a site. Fitted by a Laplace approximation: for given (k, tau) the regression and effects maximise the penalised NB2 log likelihood (Newton with step halving, sparse); (log k, log tau) maximise `penalised - S log tau - 0.5 log det(Z'WZ + I/tau^2)` by Nelder-Mead. Check the gradient `(y - mu) k / (k + mu)`, the weight `mu k (k + y) / (k + mu)^2`, the objective, and that the estimate applies the gamma update once.
  - `checks/candidates.py`: scores both when `classes` is given; `--reference` chooses the version compared against (default unchanged); new columns per row: `open ended`, `street effect spread`, and a count check for a fitted version scored on the crashes it was fitted to (forecast = estimate * later years / fitting years; total, Poisson deviance per intersection, and expected and seen in three bands by the forecast's order). `deviance per intersection` is summarised when present.
- Changed areas and affected producers and consumers: the two new modules; `checks/candidates.py` (`score_windows`, `paired`, `summarise`, `main`). `windows.csv` gains columns; nothing reads it but people.
- Pattern inventory: `score_windows` callers are `main` and the tests. `fit["spread_power"]` is read with a default of 2 because the textbook fits are NB2 and carry no such key.
- Verification: `make check` | working tree on 3601532 | 676 passed | slow tests deselected | bsc-implementer.
- Condition inventory:

  | Condition | Test or probe | Caught / survived / not exercised | Note |
  | --- | --- | --- | --- |
  | estimate is the gamma update | `test_estimate_is_the_gamma_update_of_the_background`, `test_street_effects_are_recovered_and_help` | caught | |
  | years enter as an offset | `test_years_only_move_the_constant` | caught | |
  | commonest class is the baseline; absent class gets no column | `test_design_leaves_out_...` | caught | |
  | street effects recovered on made-up data | `test_street_effects_are_recovered_and_help` | caught | tau within 0.25 of 0.8, correlation over 0.8 |
  | a name counted once per site | `test_membership_counts_each_street_once` | caught | |
  | fallbacks | two fallback tests | caught | |
  | forecast scaling, bands sum to totals, no forecast across groups | `test_textbook_models_are_scored_with_forecasts_when_classes_are_given` | caught | |
  | deviance formula | `test_count_check_matches_the_deviance_by_hand` | caught | |
  | a class with sites but no crash (separation) | none | not exercised | a failed fit becomes the labelled fallback |
  | k or tau at a search limit | none | not exercised | seen on real data (k at its upper limit in one window); reported, not treated as failure |
  | forecast where the estimate is 0 and a later crash occurs | none | not exercised | fitted estimates are positive |

- Settled decisions (do not re-report): the predictor set (from the outside brief, no feature search); streets told apart by name; plug-in estimates without the effects' uncertainty; later years as whole calendar years with `open ended` flagged.
- Known limitations and out of scope: Laplace with the regression found alongside the effects (as lme4 nAGQ = 0), not the full Laplace over the effects alone; no standard errors.

## Review, round 1 — textbook-models-1

Verdict: **changes required** (round 1).

- **TB-001 — confirmed, medium:** `checks/candidates.py`, `main()` --reference choices and `paired()` fitted-reference filter. Neither newly added textbook challenger can be selected as the comparison reference: argparse allows only keys of VERSIONS, which contains only the street-model power variants. Even a direct `summarise(..., reference=STANDARD)` or STREET_EFFECTS call discards all its valid reference fits because `paired()` requires method == cross.FITTED ("street-length model"), while the new fit methods are "standard empirical Bayes" and "street-effects model". Concrete case: `--reference "Standard empirical Bayes"` is rejected; bypassing the parser still yields no paired rows despite a converged standard model. Include the new fitted versions in reference choices and recognize their fitted method labels while excluding fallbacks. Add tests selecting each new challenger as reference and retaining only its successfully fitted windows.
- **TB-002 — confirmed, medium:** `checks/candidates.py`, `score_windows()` fitting-years and forecast-ratio calculation. Exposure arithmetic is performed unconditionally without requiring positive fitting and testing periods. With a supported open-ended window [2022, 2023, None] but the last placed crash in 2019, `last - test_from + 1` is -3; a positive fitted estimate becomes a negative expected later count (and an invalid negative deviance when later counts are zero). Separately, when first_year is omitted and hits begin in 2020, the valid window [2019, 2020, 2022] gives zero fitting years and divides by zero before the fitted flags are checked, even though every version should simply fall back from zero training counts. These windows were harmless for ranking-only scoring before forecast calculations were added. Guard unavailable/nonpositive periods and leave count diagnostics missing or handle the window explicitly; never emit negative forecasts or divide by zero for an unfitted window. Add coverage for no later period and no earlier training records.

Other review: the ordinary NB2 offset, road-class indicators and gamma update are consistent with the stated textbook model. Reviewed the street membership matrix, Newton gradient/weight, penalty, determinant term and final single gamma update against the handoff, respecting the settled plug-in/Laplace approximation scope. No separate correctness finding in those model formulas.

Validation: executed the exact argparse reference-option statement: both new challenger names were rejected. Executed the exact reference-method filter with controlled frame stand-ins: street-model fits survived and both textbook fit labels were removed. Executed the exact ratio assignment: a 2023-start open-ended window ending in 2019 produced -0.375 for eight fitting years (turning an estimate of 10 into -3.75), and zero fitting years raised ZeroDivisionError. Checked NB2 gradient and curvature against scalar finite differences at three made-up count/mean/shape combinations; all passed. Reviewed the staged source/tests and call paths. These are isolated control-flow/arithmetic checks, not pandas/numpy/SciPy/statsmodels integration runs. Full `make check` was not rerun; the handoff reports 676 passing tests. No protected files or records were opened.

Finding ledger: TB-001 open; TB-002 open. Test each finding before changing staged files, then request round 2 with a fresh snapshot. Implementer releases the reviewer lock. Review does not authorize commit, push or merge.

## Handoff, round 2

- Round 2 of at most 3. Snapshot: `/tmp/bsc-review/textbook-models-r2/`. Loop clock restarted; expires (UTC) `2026-11-24T02:26:32Z`.
- TB-001: confirmed and fixed. `FITTED_METHODS` holds the three fitted labels and `paired` keeps a reference whose method is any of them; `--reference` offers both textbook versions. Test: `test_a_textbook_model_can_be_the_reference` (both versions; a fallen-back reference is still left out). It failed before the fix.
- TB-002: confirmed and fixed. With no fitting years the textbook versions are not fitted (labelled fallback "no fitting years"), and no forecast is made unless the fitting period and the later period are both at least a year. Test: `test_no_forecast_without_a_fitting_period_or_a_later_one`.
- Also changed, found while writing the TB-001 test: on a made-up city with no street effects and no spread of rates, `fit_street_effects` failed with "did not converge". The search clipped log k and log tau to their limits inside the objective, so the objective was flat beyond a limit and Nelder-Mead wandered there. The limits are now passed to Nelder-Mead as bounds and the clipping is gone; the same case converges with k at its upper limit. Nothing else in the model changed.
- Verification: `make check` | working tree on 3601532 | 679 passed | slow tests deselected | bsc-implementer.

## Review, round 2 — textbook-models-1

Verdict: **accepted** (round 2). No new correctness findings.

- **TB-001 — closed, fixed:** both textbook versions are now CLI reference choices. The pairing filter accepts the three fitted method labels and excludes count-only/blend fallbacks. The new parametrized reference regression covers both challengers and a fallen-back reference.
- **TB-002 — closed, fixed:** absent/nonpositive fitting or later exposure produces a missing ratio, and count diagnostics require a positive ratio. Textbook models with no fitting years receive a labelled fallback instead of an invalid fit. The regression covers both missing training exposure and an open-ended window beyond the records.

Also reviewed the street-effects optimizer adjustment: it passes LOG_SHAPE/LOG_TAU as explicit Nelder-Mead bounds, clips the initial log shape into its permitted range, and uses the bounded values directly in the objective/final fit. This removes the former clipped-objective plateau without changing the specified parameter ranges.

Validation: executed the exact argparse reference statement and reference-method filter with controlled inputs; both challenger names were accepted, all three fitted labels survived, and both fallback labels were excluded. Executed the exact later-years, ratio and count-check gating statements for zero/negative fitting exposure, absent/negative later exposure and a valid period. Invalid cases made no count-check call; the valid case preserved the expected ratio. Executed the exact street optimizer call with an inert minimizer to verify explicit bounds and a bounded initial log shape. Reviewed the no-fitting-years branch and added regressions. These are isolated checks, not full pandas/numpy/SciPy/statsmodels integration runs. Full `make check` was not rerun; the handoff reports 679 passing tests. No protected files or records were opened.

Final ledger: TB-001 closed; TB-002 closed; no open findings. Loop textbook-models-1 complete. Implementer releases the reviewer lock. Acceptance does not authorize commit, push or merge.
