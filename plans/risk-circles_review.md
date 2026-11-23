# Review: risk-circles

## Current state

- Status: complete (round 2 accepted)
- Base commit: `84bb1da`; snapshot: `/tmp/bsc-review/risk-circles-r1/`
- Decisions needed from the user: none

## Loop

- Loop ID and round: `risk-circles-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-risk-circles`
- Reviewer: `bsc-reviewer` (Codex)
- Authorized scope: review requests and replies only
- Expires (UTC): 2026-11-23 05:44

## Handoff, round 1

- Tier: Medium. Two requests from the user for the crash map's predicted-risk view.
- First request, **risk circles**: `ranking.circles(path, years, floor=0.5)` returns `{"y": "first–last", "c": [[lat, lon, expected], ...]}` for the city's intersections (same in-city rule as `top`, now shared as `_in_city`) whose `expected_bike_crashes` is at least 0.5. The blend leaves `expected` empty, so it gets no circles. The template draws them in `rkLayer`, beneath the numbered markers, as non-interactive circleMarkers with radius `max(2, 3.2*sqrt(e))` (area follows expected crashes) in one colour. A key with reference sizes 1, 5 and 20 (those up to the city's maximum) goes in the panel and the printed key.
- Second request, **ranks run 1 to n within the city**: Markers carry `c` (position in the city list) as well as `r` (the area rank). The marker number, popup and table use `c`. Where the area ranks are not 1..n (`GAPS`, `_gaps`), the popup, panel table and one-pager add the area rank ("Rank in area"). The one-pager and print key wording changed to match; the old "gaps are corners outside the city" line is gone.
- Wiring: `movement.page`/`build` take `circles` and fill `/*CIRCLES*/` via `compact`. `__main__` computes `years` before the map and passes `ranking.circles(...)` when `--ranking` is given.
- Tests: `tests/test_report_ranking.py` covers city and area ranks in markers and the one-pager (with and without gaps) and the circle filter (outside the city, empty expected, floor). `make check` passed.
- Real builds (counts only): Los Altos has 63 circles, its one-pager numbered 1.. with area ranks 7, 10, ..., and the print checked. San Francisco has 1,849 circles, numbered 1..20, with no area column.
- Please check: `zip(..., strict=True)` alignment in `circles`, the JS when CIRCLES is empty (blend or no ranking), and that `GAPS` and `_gaps` agree.
- Status: ready for reviewer

## Review, round 1 — risk-circles-1

Verdict: **changes required** (round 1).

- **RC-001 — confirmed, medium:** `src/bike_safety_ca/report/__main__.py:78`, unconditional `years` calculation. The new placement executes `int(crashes.year.min())` even when no ranking was requested. An empty crash table (for example, a selected area with no crashes after the first-year filter) returns a missing minimum and raises `ValueError: cannot convert float NaN to integer`, so `report map --config ...` now aborts before `movement.build()`. Before this change, year extraction occurred only for the optional ranking output, and the map builder explicitly supports empty input by drawing streets alone. Calculate years only in the ranking path, and handle an empty crash range explicitly if that path needs to support it. Add a CLI-level regression for an empty loaded crash table with no `--ranking`.

Other checks: `circles()` applies the same city filter and sort to both locations and expected counts, then masks both in the same order; the strict zip remains aligned. `_gaps` and `GAPS` make equivalent comparisons for the sorted integer ranks emitted by `top()`/`markers()`. City positions are assigned in row order and displayed consistently in markers, popups, table and Markdown, with area ranks retained where they differ. No additional correctness finding in those paths.

Validation: executed the exact extracted CLI `main()` with controlled empty-crash and I/O stand-ins, map-only arguments and no ranking: it raised ValueError and never called the map builder. Removing only the newly unconditional year assignment in memory allowed the same scenario to call the builder and return. Executed the changed JavaScript risk block in Node with made-up no-ranking, blend, contiguous-city-rank and gapped-area-rank inputs: circle counts, finite radii, non-interactive circles, empty-key handling, city numbering, conditional area column and popup escaping passed. Reviewed the Python circle filter and rank tests; full pandas/geospatial/browser integration checks were not rerun. The handoff reports `make check` passed. No protected files or records were opened.

Finding ledger: RC-001 open. Test the finding before changing staged files, then request round 2 with a fresh snapshot. Implementer releases the reviewer lock. Review does not authorize commit, push or merge.

## Handoff, round 2

- Snapshot: `/tmp/bsc-review/risk-circles-r2/`. Round 2 of at most 3.
- RC-001 confirmed before fixing: the new CLI test (`test_the_report_command_draws_the_streets_alone_with_no_crashes`: `crash_table.load` patched to return no rows, `report map` run with and without `--ranking`) failed on round 1 with `ValueError: cannot convert float NaN to integer`.
- Fix: `years` is None when the crash table is empty. `ranking._period(years)` gives "first–last", or "the years used" when there are none. `circles`, `markdown` and `write` take `years: tuple[int, int] | None`; `markdown` now takes the tuple in place of `first, last`. This also covers `--ranking` with no crashes, which failed the same way before this change.
- Also fixed since round 1: a mypy error in `circles` (`float()` on an itertuples value). The columns are now masked and converted with `astype(float).tolist()`, zipped strictly; same rows, same order.
- Checks: the new test passes, and `make check` passed (631 tests).
- Status: ready for reviewer

## Review, round 2 — risk-circles-1

Verdict: **accepted** (round 2). No new correctness findings.

**RC-001 — closed, fixed:** the CLI guards year extraction with `len(crashes)`, passing None when the input is empty. The ranking path accepts that value consistently in `circles`, `write` and the revised `markdown` signature, with `_period` supplying a nonnumeric label. The new command regression exercises an empty loaded crash table with and without ranking and verifies the generated map and one-pager. Reviewed callers of the changed Markdown signature; they have been updated.

Also reviewed the circle-column conversion: latitude, longitude and expected counts use the same mask and retain the same sorted row order before strict zipping. This preserves alignment while avoiding the reported itertuples typing issue.

Validation: executed the exact extracted CLI `main()` with controlled I/O stand-ins for four scenarios (empty/populated crashes, each with/without ranking); all reached the map builder, and ranking calls received the expected None or year tuple. The empty stand-in rejects any attempt to compute its minimum/maximum, confirming the guard is effective. Executed the exact `circles()` and `_period()` functions with column stand-ins covering missing expected values, below-floor values, the inclusive 0.5 threshold and all-empty blend estimates; alignment and output passed. These are isolated control-flow checks, not full pandas/geospatial integration tests. Full `make check` was not rerun; the handoff reports 631 passing tests. No protected files or records were opened.

Final ledger: RC-001 closed; no open findings. Loop risk-circles-1 complete. Implementer releases the reviewer lock. Acceptance does not authorize commit, push or merge.
