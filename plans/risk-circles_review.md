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

## Loop risk-circles-2: circles only, clickable

- Loop ID and round: `risk-circles-2`, round 1 of at most 3. Implementer: `bsc-implementer`, pane `wF:p1`. Expires (UTC): 2026-11-23 06:04.
- Base: `238ba2f` (loop 1's accepted commit). Snapshot: `/tmp/bsc-review/risk-circles2-r1/`; `staged.diff` is against that commit.
- Purpose, as the user asked: remove the numbered black ovals so the risk view shows only the expected-crash circles; clicking a ranked-list row opens that corner's popup on the map; clicking a circle shows its rank when it has one.
- Changes:
  - `ranking.circles` rows gain the street names: `[lat, lon, expected, streets]`.
  - Template: the circles are interactive. A circle at a ranked corner (matched on lat/lon to 5 decimals; both come from the same CSV, rounded to 6) gets a thicker outline and the rank popup (city rank, area rank when `GAPS`, and `why`). Other circles say "about X bike crashes over Y".
  - A ranked corner with no circle (blend, or expected below the floor) gets an unfilled outline circle so it can still be found.
  - The `rk` divIcon markers and `.rk` CSS are removed. A delegated click on `#panel tr[data-rk]` sets the view (zoom at least 16) and opens the circle's popup; it does nothing outside risk view.
  - The print key and panel note are reworded.
- Checks: `make check` passed. Headless Chrome on a real build (counts only): no ovals, 1,850 interactive paths, and clicking row 1 opened the rank 1 popup, with no script errors.
- Please check: the lat/lon key matching, the panel listener when the panel is rebuilt by `draw()` (delegated, so it should be fine), and the blend case with an empty `CIRCLES.c`.
- Status: complete (round 1 accepted)

## Review, round 1 — risk-circles-2

Verdict: **accepted** (round 1). No blocking correctness findings.

Reviewed removal of the numbered divIcon markers, interactive circle popups, fallback outlines, and delegated ranked-row clicks. Ranked and circle coordinates are both emitted from the same CSV with six-decimal rounding and use the same JavaScript lookup-key function. The street-name column uses the same mask/order as the other strictly zipped circle columns. Popup names and explanations are escaped. The listener is attached to the persistent panel element, so replacing its contents during redraw does not remove it; it resolves the circle before changing the map view and opening the popup. Empty circle data still yields fallback outlines for ranked corners.

Validation: executed the exact changed JavaScript risk block in Node with DOM/Leaflet stand-ins for no ranking, blend-only ranking, ranked and unranked expected circles, and a ranked corner below the circle threshold. Checks passed for circle/fallback counts, ranked-circle lookup, popup escaping, row navigation with zoom at least 16, opening the corresponding popup after a simulated panel redraw, retaining the delegated listener, and ignoring row clicks outside risk view. Reviewed the updated Python output-shape assertions and shared-coordinate provenance. These isolated checks are not a full browser/geospatial integration run. Full `make check` was not rerun; the handoff reports it passed. No protected files or records were opened.

Ledger: no open findings in risk-circles-2; RC-001 from risk-circles-1 remains closed. Loop risk-circles-2 complete. Implementer releases the reviewer lock. Acceptance does not authorize commit, push or merge.

## Loop risk-circles-3: per-city circle scale, screen-only note

- Loop ID and round: `risk-circles-3`, round 1 of at most 3. Implementer: `bsc-implementer`, pane `wF:p1`. Expires (UTC): 2026-11-23 06:21.
- Base: `897bb4a` (loop 2's accepted commit). Snapshot: `/tmp/bsc-review/risk-circles3-r1/`; `staged.diff` is against that commit.
- Purpose, as the user asked after seeing prints:
  - The printed risk view must not say "Click a row to find the corner on the map": that note gets class `screen`, hidden by `@media print` and `body.printing`.
  - Circle size is scaled to the city's highest expected count, so a small city's top corners show as clearly as a large city's: `rr(e) = max(2, 16*sqrt(e/CMAX))` (`CMAX||1` guards an empty list).
  - The key picks up to three reference sizes from 0.5, 1, 2, 5, 10, 20, 50 and 100 that lie within [CMAX/10, CMAX].
- Accepted trade-off: equal circle sizes no longer mean equal counts across cities; the key states each map's sizes.
- Checks: `make check` passed. Real Los Altos and San Francisco builds were printed: the note is absent from both PDFs' text, and the keys show 1, 2, 5 and 5, 10, 20.
- Please check: `rr` is defined before `CMAX` in the same `const` statement, but it is only called later, so there's no TDZ issue; the key list when CMAX < 0.5 (empty `CIRCLES.c`: the key is not drawn); and that `body.printing` is the class the print path sets.
- Status: complete (round 1 accepted)

## Review, round 1 — risk-circles-3

Verdict: **accepted** (round 1). No blocking correctness findings.

The `rr` arrow function closes over `CMAX` but is invoked only after the declaration has initialized that value; the new ordering does not cause a temporal-dead-zone error. The per-city maximum has radius 16, with the radius-2 minimum retained. Reference sizes follow the specified candidate list, interval filter and final-three selection. The ranked-list instruction has the `screen` class; both native print media and the existing `body.printing` layout hide it.

Validation: executed the exact changed scale/key JavaScript in Node for empty data and maxima 0.5, 0.9, 1, 7, 30, 100 and 1000. All completed without initialization errors; radii stayed finite, each nonempty maximum had radius 16, reference counts remained at most three, and the empty-data key was absent. Checked the instruction markup and CSS selectors against the print functions' actual addition/removal of the `printing` class. Full browser/PDF checks and `make check` were not rerun; the handoff reports both were checked by the implementer. No protected files or records were opened.

Ledger: no open findings in risk-circles-3; RC-001 remains closed. Loop risk-circles-3 complete. Implementer releases the reviewer lock. Acceptance does not authorize commit, push or merge.
