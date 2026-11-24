# Review: evaluation-code

## Current state

- Status: ready for reviewer
- Base commit: `baa5745` (branch `evaluation`, from `model-review`); snapshot: `/tmp/bsc-review/evaluation-code-r1/`
- Decisions needed from the user: none

## Loop

- Loop ID and round: `evaluation-code-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-evaluation`
- Reviewer: `bsc-reviewer` (Codex), pane `wF:p2`
- Expires (UTC): `2026-11-24T22:17:39Z`

## Handoff, round 1

- Tier: Standard
- Intended behaviour: the first code for the accepted evaluation design (`plans/evaluation-plan_review.md`; the plan itself is outside the repository).
  1. `model/crash_history.top_capture`: the plan's primary measure (11.5): mean over budgets 1..ceiling of the share of later crashes at the top, ties sharing places, not a number when there is no later crash or no place. Must equal the mean of `top_share(k)` over k divided by the later total.
  2. `checks/candidates`: a `capture at the top` column (percent) and measure; `top_places` computes 5% rounded up in whole numbers. This replaces `math.ceil(0.05 * n)`, which gave 8 for 140 sites through floating point; existing `top 5% share` figures can move by one place in such areas. Intended.
  3. `checks/reporting.minor_injury_change`: the plan's reporting check by severity (12.3, 12.4): minor-injury crashes per year 2021-2024 over 2016-2019, flagged under 0.5 or over 1.5, not assessable for a missing year, no earlier minor-injury crash, or over 10% of a period ungraded (that 10% line is new here, not in the plan). Printed by the reporting command.
  4. `checks/assignment`: selection or final test from a SHA-256 of a fixed salt and the unit's smallest Census place code (11.7).
  5. `config/held_back/{selection,final_test}/*.yaml`: 64 generated city configs, in subfolders so that commands globbing `config/*.yaml` do not score them, with a README.
- Not in this change: the group bootstrap, the decision rule, the blend fallback for street context, the car-only floor, the pooled aggregate, the off-highway ratio. The comparison command's present gates are unchanged.
- Verification: `make check` passes (lint, mypy, 697 tests). All 64 configs load. Tests use made-up data.
- Settled decisions (do not re-report): the design, thresholds, salt and the assignment it produced; configs for final-test cities being in the repository.
- Known limitations: the configs' latitude and longitude boxes are the Census outline padded by 0.2 degrees; `ccrs_cities` spellings were taken from CCRS city totals and checked by download for one city only so far.

## Review — evaluation-code-1, round 1

Verdict: **changes required, round 1**. One confirmed correctness finding blocks acceptance of the assignment helper's declared iterable interface.

### EC-001 — consume unit iterables only once (confirmed, blocking, medium)

Location: `src/bike_safety_ca/checks/assignment.py:43–54`, especially the validation loop at 49–50 and the second traversal at 54.

`assign` accepts `Mapping[str, Iterable[str]]`, but consumes each iterable while checking duplicate place codes, then passes that same iterable to `which_set`. One-shot iterators/generators are exhausted by then. A valid nonempty agency group fails rather than receiving its deterministic assignment:

```python
assign({'made-up agency': ['00010', '00020']})
# {'made-up agency': 'final test'}
assign({'made-up agency': iter(['00010', '00020'])})
# ValueError: a unit needs at least one place code
```

Reproduced directly by executing the snapshot assignment module with the standard library; tuples also work while generators fail. This is an implementation failure for an explicitly supported input type, not a criticism of the settled salt or produced city assignments. Materialize and normalize each unit once, then use the same stored collection for duplicate validation and hashing. Preserve the duplicate-city and genuinely empty-unit errors. Add a regression covering generator-valued units, with the same result as list-valued units.

### Other reviewed behavior and scope

The new capture implementation's tied-block means and descending budget weights match the accepted average-over-budgets formula for finite rankings and nonnegative aligned counts. Its zero/empty return and percent conversion in `score_windows` are consistent with the stated scope. The reporting helper retains separate not-assessable outcomes for absent years, excessive ungraded severity and no earlier minor events, uses strict threshold comparisons, and excludes 2020. Its documented city-total limitation is appropriately explicit. The new 10% ungraded threshold is acknowledged in the handoff; this review does not independently validate it as a reporting-completeness cutoff.

Deferred evaluation features and inherited comparison gates were explicitly excluded from this change, so their absence is not re-reported as a defect. These additions alone do not make the existing comparison command ready for held-back selection/final scoring under the complete design.

### Verification

- Executed the actual assignment module against list, tuple and generator units; reproduced EC-001.
- Parsed all 64 held-back YAML configs (22 selection, 42 final): checked each declared Census code against the unchanged hash, primary window, first year, one municipality and ordered bounding coordinates. All hash checks pass. Confirmed that the existing default config discovery uses nonrecursive `glob('*.yaml')`, excluding the held-back subfolders.
- Executed the actual `top_places` function extracted from the snapshot AST: it equals integer ceiling(n/20) for every n from 0 through 10,000.
- Read the relevant code and added tests. Did not rerun pytest or `make check`: this review environment lacks NumPy, pandas and pytest. The handoff reports 697 passing tests; that result was not independently reproduced. No real city was built, fitted or scored, and no protected paths or records were opened.

Ledger: EC-001 open. Request round 2 with a fresh snapshot after confirming/fixing the finding. Implementer releases the reviewer lock. This review does not authorize a commit, push, merge or held-back evaluation run.

## Handoff, round 2

- Implementer: `bsc-implementer`, pane `wF:p1`. Snapshot: `/tmp/bsc-review/evaluation-code-r2/`. Round 2 of at most 3. Expires (UTC): `2026-11-24T22:20:55Z`.
- EC-001: confirmed and fixed. `_codes` normalises a unit's codes once (five digits, each once, at least one); `assign` reads every unit once and reuses the list for the duplicate check and the hash; `position` uses the same helper. Regression test with generator and iterator units, and an empty unit through `assign`.
- Nothing else changed. `make check` passes (697 tests).

## Review — evaluation-code-1, round 2

Verdict: **accepted, round 2**. No open correctness findings remain for the staged scope.

**EC-001 closed.** `checks/assignment.py` now materializes each unit through `_codes` before validation, then reuses those lists for duplicate detection and hashing. The regression covers generator/iterator parity and rejection of an empty unit. The change preserves the fixed salt and hash results.

Verification: executed the snapshot assignment module directly. Confirmed identical assignments for list, generator and iterator inputs; used an iterable that raises on a second iteration to confirm each original input is read exactly once; checked normalization, duplicate-code rejection and empty-iterator rejection. The fixed hash examples and all 64 config-to-set assignments still pass. Read the revised helper and regression test, and checked the round-2 handoff against the prior finding. No new regression found.

The handoff reports `make check` passing (697 tests). Full pytest/make checks were not independently repeated because this review environment lacks NumPy, pandas and pytest; the focused standard-library checks above did run. No real records or protected paths were opened and no city was built, fitted or scored.

Ledger: EC-001 closed; evaluation-code-1 ends accepted at round 2. Acceptance covers these initial additions, not the deferred group bootstrap, decision rule, fallback changes, pooled aggregate or removal of inherited comparison gates. The implementer releases the reviewer lock. Review does not authorize a commit, push, merge or held-back evaluation run.
