# Review: power-one

## Current state

- Status: complete (round 2 accepted)
- Next action: none
- Base commit: `79fb6cf`; snapshot: `/tmp/bsc-review/power-one-r1/`
- Open findings: none (PO-001 and PO-002 closed)
- Decisions needed from the user: none

## Loop

- Loop ID and round: `power-one-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-model-review`
- Reviewer: `bsc-reviewer` (Codex), pane `wF:p2`
- Authorized scope: review requests and replies only
- Expires (UTC): `2026-11-24T00:54:58Z`

## Handoff, round 1

- Tier: Standard
- Intended behavior and acceptance criteria:
  - New command `python -m bike_safety_ca.checks.candidates`: refits versions of the street crash model (spread power fitted, 1, 2) on every built city's hold-out windows through `rank_intersections`, and scores them with past bike crashes and the blend. One row per city, window, version, crashes fitted to and crashes scored on, unrounded, in `windows.csv`; `summary.csv` pairs each version with the reference (power fitted) by city and window and gives the mean over windows, the mean over cities, 5th and 95th percentiles from drawing whole cities again (10,000 draws, fixed seed), the range leaving one city out, and cities lower; `run.json` has the code revision and a hash of each crash table. `--also name=folder` adds an area summarised apart (the Los Altos study area overlaps cities).
  - An all-cyclist ranking is scored on later child crashes with the same score vector; a child-fitted ranking is a separate fit.
  - Model change: `SPREAD_POWER = 1.0` in `model/crash_history.py` is the default of `rank_intersections`; `None` still fits the power. `fit_street_model` keeps its own default (fitted), so research code asks explicitly.
  - Callers: `model/ranking.py` (all cyclists and children), `checks/holdout.py`, `checks/attainable.py`, `checks/bike_routes.py` use the default (the flagged fit in bike_routes now passes `SPREAD_POWER` so it matches its base). `model/corridors.py` passes `spread_power=None` on purpose: the corridor table sums expected counts and was not part of the comparison. The between-intersection corridor model is untouched.
  - `intersection_ranking.csv` gains a `spread_power` column (empty for the blend); `docs/guide.md` lists it.
- Changed areas and affected producers and consumers: `rank_intersections` and every caller above; the ranking file's columns (read by name by the report); `case_studies/los_altos/expected_holdout.csv`.
- Pattern inventory: every `rank_intersections` and `fit_street_model` call in `src` was checked (list above); none other exists.
- Verification: `make check` | staged tree on 79fb6cf | 663 passed | slow tests deselected | bsc-implementer. Real runs (aggregate only): the command on 28 cities; power 1 minus fitted, 62 windows in 23 cities, all cyclists: rank score -0.0003 (5th to 95th percentile -0.0007 to +0.0002), top 50 +0.07 points, top 5% +0.19 points; child-fitted, 18 windows in 7 cities: +0.0003, -0.17, -0.19. The Los Altos rows reproduce an earlier one-off script exactly.
- Condition inventory:

  | Condition | Test or probe | Caught / survived / not exercised | Note |
  | --- | --- | --- | --- |
  | Default power is 1; None fits | `test_rank_intersections_passes_the_spread_power_on` | Caught | also checks eb equals (mu + alpha y) / (1 + alpha) |
  | Ranking file records the power; empty for blend | `tests/test_ranking.py` (two added asserts) | Caught | |
  | Corridors keep the fitted power | `test_the_corner_part_of_a_corridor_keeps_the_fitted_spread_power` | Caught | |
  | Fitted-power version stays fitted in the harness | `test_each_version_is_fitted_with_its_own_spread_power` | Caught | |
  | Child scoring reuses the all-cyclist vector | `test_a_ranking_scored_on_children_is_the_one_fitted_to_everyone` | Caught | |
  | Later crashes do not reach a fit | `test_later_crashes_do_not_reach_the_fit` | Caught | |
  | Unrounded output | `test_scores_are_not_rounded` | Caught | |
  | Pairing, both means, leave-one-out, seed | `test_summary_pairs_windows_and_weighs_cities_both_ways` | Caught | |
  | Only fitted-reference windows with enough later crashes are paired | `test_only_windows_with_...` | Caught | |
  | `main` of the new command | not exercised by a test | Not exercised | run on real tables only |

- Settled decisions (do not re-report): power 1 for the intersection rankings (all cyclists and children) is the user's and an outside reviewer's choice on the comparison above; corridors stay on the fitted power until compared; the pull (20), the 100-crash threshold and the car term are unchanged; documentation of the model (`docs/forecasting_model.md`, the case study's quoted figures) follows in a separate docs change.
- Changed expected values, with reasons:
  - `case_studies/los_altos/expected_holdout.csv`: regenerated at power 1. 11 of 66 rows change, all of them model rows ("Street-length model", "All-cyclist ranking"); the baseline rows are identical. Rank score moves by 0.002 at most on the study area and by +0.012 inside the Los Altos city limit after 2022. Largest count change: the child-fitted model after 2018 finds 4, not 10, of 87 later child crashes in its top 25 (top 50 unchanged at 14, top 100 up 2).
  - `tests/test_synthetic_holdout.py`: the last assertion required the all-cyclist and child rankings to find different counts in the top 100 in every window; at power 1 both find 15 in one window of the made-up city. It now requires the rows to differ in some figure, which is what the test is about.
  - `tests/test_ranking.py`: a stub of `fit_street_model` accepts the new keyword.
- Known limitations and out of scope: the windows are development windows and overlap; the percentiles describe sensitivity to the set of cities only.

## Review, round 1 — power-one-1

Verdict: **changes required** (round 1).

- **PO-001 — confirmed, medium:** `src/bike_safety_ca/checks/candidates.py:192–218`, `summarise()`. Missing per-measure comparisons become zero-valued bootstrap/leave-one-city-out results because zero denominators are replaced with 1. Concrete case: city A has a +0.04 difference for “rank score, no past bike crash”, city B has no defined value for that measure. A bootstrap draw containing only B is recorded as 0, even though it contains no observation; with two cities this occurs in one quarter of draws and can force the lower percentile to zero. Leaving A out likewise invents a zero comparison. If every city lacks a measure, the output has zero windows but percentile bounds 0 and leave-one-out bounds +inf/-inf. Missing subset AUCs are legitimate (no positive or no negative later sites), so this affects supported inputs. Compute each measure's resampling from eligible values/cities, or exclude zero-denominator replicates, and mark unavailable bounds as missing. Leave-one-out summaries must also exclude cases with no observations left. Add partial-missing, all-missing and one-eligible-city cases; the existing test checks only the all-missing window count.
- **PO-002 — confirmed, medium:** `src/bike_safety_ca/checks/candidates.py`, `summarise()` empty return and `main()` display via `summary.measure` (also the separate-area summary column selection). When no window has a fitted reference and enough later crashes, `paired()` yields no groups, `summarise()` returns a zero-column DataFrame, and the CLI raises AttributeError at `summary.measure` after writing partial output. Concrete case: run the new command against one built small city with fewer than 100 training bike crashes in every window; all versions properly fall back, but the comparison command then crashes instead of reporting that no paired model comparisons are available. The same issue can occur for an `--also` area with no eligible reference windows. Preserve the summary schema when empty and handle/report empty summaries in both output paths. Add a main-level no-eligible-reference regression.

Other review: checked every staged `rank_intersections`/`fit_street_model` call site, default-power propagation, explicit fitted-power corridor override, bike-route flagged/base consistency, ranking spread-power column and stated expected-value changes. No correctness finding in the requested power-setting change; the settled model-choice decision is not challenged.

Validation: executed the exact extracted bootstrap/leave-one-out arithmetic with minimal array stand-ins. With totals [0.04, 0] and valid counts [1, 0], a missing-only draw and leaving the valid city out both returned 0; all-missing draws also returned 0. Executed the exact `summarise()` no-group path with frame stand-ins, confirming an empty row/schema result, then its CLI display expression, confirming the missing-measure failure. Executed the exact `rank_intersections()` with a controlled fit: default power 1 and explicit None were forwarded correctly, and an under-threshold input retained blend fallback. Reviewed the new harness and tests. These are isolated control-flow/arithmetic probes, not pandas/numpy/SciPy integration runs; full `make check` and real-data comparison runs were not repeated. The handoff reports 663 passing tests. No protected files or records were opened.

Finding ledger: PO-001 open; PO-002 open. Test each finding before changing staged files, then request round 2 with a fresh snapshot. Implementer releases the reviewer lock. Review does not authorize commit, push or merge.

## Handoff, round 2

- Snapshot: `/tmp/bsc-review/power-one-r2/`. Round 2 of at most 3.
- PO-001 (missing counted as zero): confirmed with `test_a_city_without_a_measure_is_missing_from_it_not_zero`, which failed before the fix (5th percentile 0.0 where 0.02 was expected). A draw, or a set with one city left out, that holds no window with the measure now has no mean (`_mean`), and percentiles and the leave-one-out range are taken over the values that exist (`_edge`), missing when none does. Leave-one-out is over the cities that have the measure.
- PO-002 (nothing to compare): confirmed with `test_nothing_to_compare_gives_an_empty_summary_with_its_columns`, which failed before the fix. `summarise` always returns the `SUMMARY` columns, and the command prints through `shown`, which says "no window has a fitted reference and enough later crashes" for an empty summary, for the cities and for an area summarised apart.
- Checks: `make check` passed (665 tests).

## Review, round 2 — power-one-1

Verdict: **accepted** (round 2). No new correctness findings.

- **PO-001 — closed, fixed:** `_mean` marks zero-observation averages as missing, and `_edge` reduces only existing values. Missing-only bootstrap samples no longer insert zero differences; leave-one-out cases with nothing left are unavailable; all-missing measures return missing bounds. The added regression covers a city with missing subset AUC, one eligible city and an entirely missing measure.
- **PO-002 — closed, fixed:** `summarise()` returns the explicit SUMMARY schema even with no paired rows. `shown()` handles empty summaries before formatting, and both the city and separate-area command output now use it. The regression verifies the empty schema and explanatory message.

Validation: executed the exact `_mean`/`_edge` functions with minimal numeric-array stand-ins for partially missing draws, all-missing draws and a one-city leave-out. Missing values stayed missing, valid-only extrema were preserved and no reduction was attempted when all values were missing. Executed the exact `summarise()` no-group path and `shown()` with frame stand-ins: the empty result retained all SUMMARY columns, and both the full display and the separate-area column selection returned the explanatory message. Reviewed the revised summary loop, new regression tests and staged caller/model changes. These are isolated arithmetic/control-flow checks, not pandas/numpy/SciPy integration runs. Full `make check` was not rerun; the handoff reports 665 passing tests. No protected files or records were opened.

Final ledger: PO-001 closed; PO-002 closed; no open findings. Loop power-one-1 complete. Implementer releases the reviewer lock. Acceptance does not authorize commit, push or merge.
