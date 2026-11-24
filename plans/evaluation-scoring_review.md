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
