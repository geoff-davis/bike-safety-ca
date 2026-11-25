# Review: evaluation-scoring

## Loop

- Loop ID and round: `evaluation-scoring-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-evaluation`
- Reviewer: `bsc-reviewer` (Codex), pane `wF:p2`
- Base commit: `baa5745`; snapshot: `/tmp/bsc-review/evaluation-scoring-r1/`. `staged.diff` holds only the two new files of this round; the rest of the index was accepted in `evaluation-code-1` and is in `tree/`.
- Expires (UTC): `2026-11-24T22:26:07Z`

## Handoff, round 1

- Tier: Standard
- Files: `src/bike_safety_ca/checks/evaluation.py`, `tests/test_evaluation.py`.
- Intended behaviour: the scoring command of the accepted design (sections 11 and 12 of the plan, summarised in `plans/evaluation-plan_review.md`).
  - `score_city`: one window (fit through 2020, score 2021-2024); models B, H, street context, blend, past bike, past car; outcomes all injury and fatal-or-severe; `top_capture` with 5% of intersections; every model scored in every city, with the blend where a fit fails (street context included); `larger` from fitting-year bike crashes against `MIN_CRASHES`.
  - `compare`: paired difference, equal-weight city mean over cities with a later crash or pooled by later crashes; whole agency units resampled with replacement and the aggregate recomputed; 5th and 95th percentiles; a draw with no later crash left out.
  - `verdict` and `select`: the rule of 11.1 on larger cities only (B against H, then street context against the model carried forward; inconclusive keeps B).
  - `main`: refuses a folder named `final_test` without `--frozen`; for selection writes the choice; reports the primary (city mean, all injury) and companion (pooled, fatal or severe) comparisons.
- Verification: `make check` passes. Tests use made-up data. No held-back city has been scored.
- Known limitations, not for this round: the sensitivity result without flagged cities, the smaller stratum's pooled figure, the count-accuracy and other secondary measures, and the manifests are not built yet. The final test's two claims are computed but no pass or fail is printed for them. `cross.place` uses each config's area outline, which for these configs is the Census city outline.
- Settled decisions (do not re-report): the design, margin, window and models.

## Review — evaluation-scoring-1, round 1

Verdict: **changes required, round 1**. Three confirmed correctness findings in the new scoring command. Reviewed only the two new files and relevant snapshot dependencies; settled design choices are not reopened.

### ES-001 — B is frozen against the wrong comparator (confirmed, blocking, high)

Location: `src/bike_safety_ca/checks/evaluation.py:208–210`; the B-kept expectation in `tests/test_evaluation.py` also encodes this behavior.

When B is kept against H and street context fails to replace B, `select` returns B with CONTEXT as its comparator. The frozen non-inferiority claim then compares B with the rejected simpler challenger, rather than confirming B against H, the more flexible model for which the margin was introduced. It also does this when B-versus-H selection was inconclusive and B was retained solely as the default.

Concrete case: selection B−H interval [-0.5, +0.5], context−B interval [-3, -2] returns `(B, CONTEXT)`. On final data B could lose 3 points to H yet gain 2 points over context; the current frozen pair would satisfy its margin claim without testing the intended B-versus-H claim. If B survives, freeze H as its comparator. If H survives, freeze B; if context replaces either, freeze the model it replaced. Update the test's B-kept comparator expectation and cover the inconclusive B-versus-H branch too.

Verification: executed the actual AST-extracted `select` and `verdict` with synthetic comparison bounds; observed the wrong pair directly. No model fit or real data was used.

### ES-002 — validate the frozen choice before any final scoring (confirmed, blocking, high)

Location: `evaluation.py:227–255`.

The early check only tests that `--frozen` exists. Its contents are not read until after every city is scored and `cities.csv` is written. An existing file containing `{}`, invalid JSON, or unknown model names therefore passes the guard and exposes final scores before the command discovers that it has no usable frozen choice. This defeats the stated refusal to score final cities without a written-down choice.

Parse and validate the frozen document before calling `cross.place` or `score_city` (preferably before processing cities at all). Require valid chosen/comparator fields and permitted model names; refuse malformed, missing or otherwise unusable choices with a clear command error and no scoring or output. Test with an existing malformed/empty-object frozen file and a scoring stub that fails if invoked; the current tests cover only missing paths.

Verification: executed the actual AST-extracted `main` with in-memory path, city-loader and scoring stand-ins. For a purported existing frozen file whose contents are `{}`, the event trace was `check frozen exists`, then `SCORE CITY`; reading the JSON had not occurred. Static control flow confirms that a real run writes city scores before the later missing-key/parse failure. The harness did no filesystem writes and no data access.

### ES-003 — selection omits the severe companion against the comparator (confirmed, blocking, medium)

Location: `evaluation.py:258–265`.

For selection, `pairs` contains only `(chosen, BIKE)`, so the companion list reports the two floors but omits `(chosen, comparator)`. Section 12.2 requires that informational severe comparison beside both selection and final results. The final branch does include it, but the selection branch never computes it. For example, freezing B with comparator H produces companion entries only for B−past-bike and B−past-car, with no B−H severe interval.

Build the companion pairs explicitly from the chosen model and its comparator plus both floors in either mode, independently of the primary-pair list. Preserve its descriptive role. Add a selection-command result assertion covering all three companion comparisons.

Verification: executed the actual `main` control flow with an in-memory selection result and trace-only comparison function; the emitted companion contains only the two floors.

### Other scope and verification

The whole-unit resampling retains group multiplicities and recomputes the city/pooled aggregate on each draw. The common later counts and zero-event handling agree with the stated comparison contract. The first-stage and second-stage choice rules otherwise match the design. The listed deferred sensitivity, smaller-stratum and secondary/manifest work, and absence of printed final pass/fail, are not reported as new defects here.

Full pytest/`make check` were not independently rerun: this review environment lacks NumPy, pandas and pytest. The handoff reports passing checks. The focused standard-library AST harness exercised the actual new control flow while replacing data frames, numerical comparison results, paths and data loading with synthetic stand-ins; it does not validate pandas/NumPy integration or model-fitting numerics. No crash records or protected paths were opened, no real city was fitted or scored, and no implementation files were modified.

Ledger: ES-001, ES-002 and ES-003 open. Request round 2 with a fresh snapshot after testing the findings. Implementer releases the reviewer lock. Review does not authorize a commit, push, merge or held-back scoring run.

## Handoff, round 2

- Implementer: `bsc-implementer`, pane `wF:p1`. Snapshot: `/tmp/bsc-review/evaluation-scoring-r2/`. Round 2 of at most 3. Expires (UTC): `2026-11-24T22:30:16Z`.
- ES-001: confirmed and fixed. When B or H is chosen the comparator is the other of the two; street context is a comparator only of nothing, and has the model it replaced as its own. The test's expected pair changed from (B, street context) to (B, H) for this reason.
- ES-002: confirmed and fixed. `read_frozen` validates the file (a JSON object, `chosen` and `comparator` each one of B, H, street context, and different) and `main` calls it before any city is read; an invalid file stops with the same message and writes nothing. Tests cover an empty object, a list, broken JSON, equal models and an unknown model, through `read_frozen` and through `main`.
- ES-003: confirmed and fixed. Selection and final test now report the same pairs: chosen minus past bike crashes and chosen minus comparator for the primary result, and those two plus chosen minus past car crashes for the companion.
- `make check` passes (707 tests).

## Review — evaluation-scoring-1, round 2

Verdict: **accepted, round 2**. ES-001 through ES-003 are closed; no new correctness findings in the revised scope.

- **ES-001 closed:** B now freezes H as comparator, H freezes B, and street context freezes the model it replaced. Verified the actual selection control flow for B retained on a pass, B retained on an inconclusive first comparison, H selected, and context replacing either B or H. The test's earlier incorrect B/comparator expectation is corrected.
- **ES-002 closed:** `read_frozen` parses and validates the choice, including model identities and distinctness, before any city loading or scoring. Verified that empty objects, lists, malformed JSON, equal models and unknown models cause a command error without city loading, fitting/scoring or output. Also checked that a valid final choice is read before city loading. The new tests cover these rejected documents and a valid document with additional metadata.
- **ES-003 closed:** selection and final paths now both build primary pairs against history and the frozen comparator, and companion pairs against history, the comparator and car history. Verified the emitted result structure for both modes and that all three companion comparisons use the severe outcome and pooled aggregate.

Verification used the actual snapshot functions extracted by AST, with synthetic comparison bounds and in-memory frame/path/loading stand-ins. These checks exercised selection branches, early validation and result construction without accessing records or writing test artifacts. They do not independently verify pandas/NumPy integration or numerical fitting. The handoff reports `make check` passing (707 tests); full pytest/make checks were not rerun here because NumPy, pandas and pytest are unavailable. No protected paths were opened and no real city was fitted or scored.

Ledger: ES-001 closed; ES-002 closed; ES-003 closed. Loop evaluation-scoring-1 ends accepted at round 2. The explicitly deferred sensitivity, smaller-stratum, additional secondary measures and manifests remain outside this acceptance. Implementer releases the reviewer lock. Review does not authorize a commit, push, merge or held-back scoring run.

## Loop 2 (`evaluation-scoring-2`): handoff, round 1

- Implementer: `bsc-implementer`, pane `wF:p1`. Base commit `601e59a`. Snapshot: `/tmp/bsc-review/evaluation-scoring2-r1/` (`staged.diff` against `601e59a`, and `tree/`). Round 1 of at most 3. Expires (UTC): `2026-11-25T01:14:59Z`.
- Files: `src/bike_safety_ca/checks/evaluation.py`, `tests/test_evaluation.py`.
- Intended behaviour: the pieces the plan requires before a selection city is scored that loop 1 left out.
  - `reporting_checks`: per city, `reporting.minor_injury_change` on the merged table and the agency check's certain falls and rises in injury crashes (as `reporting.diagnose` computes them) from the first fitting year to the last scored year. `clear` only when the first is "not flagged" (so "not assessable" is not clear) and the second lists nothing. Reads counts, no ranking and no score. Restricting the agency check to certain changes in those years is a choice made here; the plan says only "the existing agency reporting check".
  - `main`: `without flagged cities` repeats the primary pairs over larger cities that are clear (a sensitivity result); `smaller cities` gives the pooled all-injury pairs over cities under the fitting threshold (descriptive); `manifest.csv` lists every scored city with its unit, sizes, later crash counts, the two checks and a hash of its crash table; `run.json` records the revision, window, margin, draws, seed and assignment salt and the configs not built.
- Verification: `make check` passes (710 tests). The command was run end to end on the 28 development cities only: 21 clear, 3 flagged by the minor-injury check, 7 with an agency year. No held-back city has been scored.
- Known limitations: `main` itself is covered by the two refusal tests and the development rehearsal, not by a unit test of a full run; `run.json` records HEAD and does not say whether the tree was clean; count accuracy and the other secondary measures are still not built.

## Review — evaluation-scoring-2, round 1

Verdict: **changes required, round 1**. Two confirmed correctness findings in the newly added outputs. The previously closed ES-001 through ES-003 remain closed.

### ES-004 — an empty clear subset aborts the entire run (confirmed, blocking, high)

Location: `src/bike_safety_ca/checks/evaluation.py:333–334`, through `compare` at lines 158–161.

Every larger city may legitimately be flagged or not assessable, especially while only a few cities are built. Then `clear` has zero rows, but the new code unconditionally calls `compare(clear, ...)`. Pivoting an empty scored table leaves no model columns, so `wide[model]` raises `KeyError`. The valid primary and companion calculations have already completed and `cities.csv` has been written, but `result.json`, `manifest.csv` and `run.json` are not written. A descriptive sensitivity subset must not make the main result unusable.

Handle zero clear cities explicitly: emit a clearly unavailable/empty sensitivity result with its city count and reason, or make `compare` return a consistent zero-city, undefined comparison without trying to access nonexistent model columns or resample zero groups. Do not substitute all cities for an empty subset. Add a command-level regression where all scored larger cities have `clear=False`, including not-assessable checks, and verify that the primary/companion result and manifests are still produced.

Verification: executed the actual AST-extracted `compare` with an empty-frame stand-in whose pivot has no model columns, matching the empty pandas shape. It raises `KeyError: 'B: spread power 1'` before aggregation. Source inspection confirms that the newly unconditional sensitivity call precedes all three final output files. No real city or record was used.

### ES-005 — smaller cities are not compared with the car-history floor (confirmed, blocking, medium)

Location: `evaluation.py:336–338`, reusing `pairs` from line 324.

The accepted smaller-city design evaluates the deployed blend against both history floors. The new smaller-city output reuses the larger primary pairs: chosen-minus-past-bike and chosen-minus-comparator. B, H and street context all fall back to the same blend under the fitting threshold, so the second comparison is identically blend-minus-blend, while past car crashes are never included. For example, choosing B with comparator H emits pooled B−past-bike and B−H, with no B−past-car result.

Construct the smaller-city descriptive pairs against BIKE and CARS, using the deployed blend (or the equivalent chosen candidate fallback). An additional candidate/comparator entry may be retained, but cannot replace the car floor. Keep these results pooled and outside the decision rule. Test a table containing smaller cities and assert that both floor comparisons are emitted.

Verification: executed the actual AST assignment that builds `result['smaller cities']`, with a nonempty synthetic smaller table and a trace-only comparison function. It emitted `(B, BIKE)` and `(B, H)`, both pooled, and no CARS comparison.

### Other scope and verification

The new `clear` predicate appropriately distinguishes not-assessable minor checks from clear cities, retains flagged cities in the main results, and labels the filtered result as sensitivity rather than a correction. The manifest retains the scored city's unit and later outcome counts, reporting results and crash-table checksum. The explicit choice to use only certain agency changes is recorded in the handoff and docstring; the existing dirty-tree/revision limitation is acknowledged rather than re-reported.

Full pytest/`make check` were not independently rerun because this review environment lacks NumPy, pandas and pytest. The handoff reports 710 passing tests and a development-only rehearsal. The focused standard-library checks used the actual new control flow with synthetic stand-ins; they do not verify pandas integration or numerical resampling. No real crash records or protected paths were opened, and no city was built, fitted or scored by this review.

Ledger: ES-004 and ES-005 open; ES-001 through ES-003 remain closed. Request round 2 with a fresh snapshot after testing the findings. Implementer releases the reviewer lock. This review does not authorize a commit, push, merge or held-back evaluation run.

## Loop 2: handoff, round 2

- Implementer: `bsc-implementer`, pane `wF:p1`. Snapshot: `/tmp/bsc-review/evaluation-scoring2-r2/` (`staged.diff` against `601e59a`). Round 2 of at most 3. Expires (UTC): `2026-11-25T01:22:07Z`.
- ES-004: confirmed and fixed. `compare` on no cities returns the comparison with no values (0 cities, not a number) instead of raising, so a set with no clear larger city, or no smaller city, still writes every output. Tested for both, and that the result still serialises.
- ES-005: confirmed and fixed. The smaller cities are compared with both floors (past bike crashes and past car crashes), pooled, never with the comparator.
- To make both testable the result assembly moved out of `main` into `report(table, units, clear, frozen)`, tested on made-up scores for the pairs, aggregates, outcomes and city counts of each result, with and without a frozen choice. `main` now reads, calls `report`, and writes.
- `make check` passes (712 tests). Rehearsed again end to end on the development cities only.

## Review — evaluation-scoring-2, round 2

Verdict: **accepted, round 2**. ES-004 and ES-005 are closed; no new correctness findings in the revised scope.

- **ES-004 closed:** `compare` now detects an empty outcome subset before pivoting or resampling and returns zero city/unit counts with undefined numerical results. The extracted `report` function preserves primary and companion results when no larger city is clear, and also handles an empty smaller-city subset. Regression tests exercise both cases and serialization.
- **ES-005 closed:** smaller-city output now explicitly compares the deployed candidate fallback against both BIKE and CARS, pooled, instead of substituting the fitted-model comparator for the car floor. The new assembly test checks both pairs and the smaller-city count.

Verification: executed the actual AST-extracted empty-comparison path with a stand-in that raises if pivoting is attempted. It returned the expected zero counts and undefined values for both outcomes. Exercised the actual `report` assembly with synthetic frame/selection/comparison stand-ins: no-clear cities, no-smaller cities, both floor pairs, retained primary/companion results, and both selection and frozen-choice paths pass. Read the refactoring, its call from `main`, and the new regression tests. These focused checks exercise control flow and result construction, not pandas integration or numerical bootstrap behavior.

The handoff reports `make check` passing (712 tests) and a repeated development-only rehearsal. Full pytest/make checks were not independently rerun here because NumPy, pandas and pytest are unavailable. No protected paths or records were opened and no real city was built, fitted or scored.

Ledger: ES-004 closed; ES-005 closed; ES-001 through ES-003 remain closed. Loop evaluation-scoring-2 ends accepted at round 2. The known remaining secondary-measure and revision/dirty-tree limitations retain their stated scope. Implementer releases the reviewer lock. This review does not authorize a commit, push, merge or held-back evaluation run.

## Loop 3 (`evaluation-scoring-3`): handoff, round 1

- Implementer: `bsc-implementer`, pane `wF:p1`. Base commit `48b9b7c`. Snapshot: `/tmp/bsc-review/evaluation-scoring3-r1/` (`staged.diff` against `48b9b7c`). Round 1 of at most 3. Expires (UTC): `2026-11-25T01:43:57Z`.
- State of the evaluation: the selection set was scored once from `48b9b7c`; B was chosen with H as comparator and written down. No final-test city has been scored.
- Change, requested by the owner before the final test: a secondary measure. `score_city` adds `best capture` (the capture of a list in order of the later crashes themselves) and `share of best` (capture as a percentage of it); `compare` takes `value` (`capture` by default, or `share of best`) and records it; `report` adds `share of best possible`, the primary pairs on that value. No decision rule, claim or existing result changes: `select`, `primary`, `companion`, the sensitivity and smaller-city results still compare `capture`.
- What to report: any way this alters an existing result or the selection rule; correctness of the best-possible value, ties and cities with no later crash included.
- Verification: `make check` passes (712 tests). Not run on any city.
- Settled by the owner (do not re-report): adding this measure after selection, as secondary only; the plan records when it was added.

## Review — evaluation-scoring-3, round 1

Verdict: **accepted, round 1**. No blocking correctness findings in this secondary-measure addition. ES-001 through ES-005 remain closed.

Ordering sites by later crash count maximizes the primary capture score: its position weights decrease monotonically, so swapping a larger count ahead of a smaller count cannot reduce capture. Equal later counts have the same contribution under any order within their tied block, and the existing fractional tie treatment therefore gives the same maximum. The new `best capture` uses the same city, outcome, denominator and treatment budget as each model score. `100 * capture / best` has the intended percent scale. For positive later totals and a nonempty budget the best value is positive; for no later crashes or no places both values are NaN and the new expression remains undefined rather than assigning zero.

The default comparison value remains raw capture. Inspection and focused execution confirm that selection, primary, companion, sensitivity and smaller-city paths still use capture by default, while only `share of best possible` explicitly requests the normalized column. The new comparison metadata identifies which value was used, including empty comparisons. No margin or verdict is applied to the new secondary output.

Nonblocking wording correction: the `score_city` docstring says “no model could match” the hindsight list. A model can happen to match its observed score, particularly with ties or simple outcomes. Say instead that it is a hindsight maximum, not a prospective benchmark that models are expected to attain. This does not affect the implemented calculation.

Verification: independently enumerated every ranking for 21 budget/count examples (including tied counts, concentrated counts and zero totals) and verified that descending later counts maximize the triangular-weight score. Executed the actual normalization expression extracted from the snapshot for ordinary, perfect and undefined values. Exercised the actual `report` and `select` control flow with synthetic frame/comparison stand-ins in selection and frozen modes, checking that normalized values are requested only for the secondary pair. Read the added tests and the changes to `score_city`/`compare`; full pandas/NumPy fitting and bootstrap tests were not independently run because NumPy, pandas and pytest are unavailable here. The handoff reports `make check` passing (712 tests).

No protected paths or records were opened and no city was built, fitted or scored. The decision to add a secondary measure after selection is treated as settled and disclosed in the handoff; this review does not authorize reconsidering that selection from the new values.

Ledger: no new blocking findings; evaluation-scoring-3 ends accepted at round 1. Implementer releases the reviewer lock. Review does not authorize a commit, push, merge or final-test scoring run.
