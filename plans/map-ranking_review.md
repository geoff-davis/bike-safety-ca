# Review: map-ranking

## Current state

- Status: complete (round 3 accepted)
- Next action: none; loop closed
- Base commit: `1b253e8`; snapshot: `/tmp/bsc-review/map-ranking-r1/`
- Open findings: none yet
- Decisions needed from the user: none

## Loop

- Loop ID and round: `map-ranking-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-map-ranking`
- Reviewer: `bsc-reviewer` (Codex)
- Authorized scope: review requests and replies only
- Expires (UTC): 2026-11-23 02:27

## Handoff, round 1

- Tier: Medium. Based on main before #18, which removes `--for`; whichever merges second will be rebased.
- Purpose, as the user asked:
  1. a model-ranking view on the crash map, switchable between recorded crashes and predicted risk;
  2. a one-page list of the top corners;
  3. the printed city view no longer ends with "and N more; zoom in to list them".
- New `report/ranking.py`:
  - `top()` keeps the N highest-ranked intersections inside the city (or all, when the ranking has no `in_city`);
  - `why()` writes a plain line from the ranking's own columns: road classes, recorded bike and car-only crashes, and the expected count when the model was used;
  - `markers()` builds the map data; `markdown()`/`write()` build the one-pager, with the PDF via `hospital.pdf.write`.
- `report` command: `--ranking CSV`, `--top N` (default 20), `--pdf`. `movement.page`/`build` take `ranked`, filled into `/*RANKED*/` via `compact`, so it is script-safe.
- Template:
  - a hidden "Show [recorded crashes | predicted risk]" select, unhidden only when there are ranked corners;
  - risk view removes the crash layer and adds the numbered markers, and the panel shows the ranked list instead of the crash tables;
  - `?view=risk` opens on risk, framed on the corners (quarter-step zoom for that fit, restored after);
  - in print, the risk view retitles the page and swaps the key for a short explanation;
  - new glossary term `ranked`.
- Print fix: a page-level `inPrint` flag, set and cleared in `toPrint`/`fromPrint`, uncaps the city-view intersection list and the crashes list, so their "and N more" notes cannot appear on paper.
- Tests: new `tests/test_report_ranking.py` (4); the page-test stand-in gains the `view` and `rkw` ids. `make check` passed (625 tests). A headless Chrome run on real data (totals only) showed:
  - the switch appears;
  - 20 markers in risk view and none after switching back;
  - no crash shapes in risk view;
  - no script errors.
- Please check:
  - `why()` against the ranking columns (`major`/`minor` NaN, the blend's empty expected count);
  - that the print-mode flag cannot stick after printing;
  - that the risk view cannot leave the crash layer off after switching back;
  - escaping of street names in markers, popups and the panel.

## Review, round 1 — map-ranking-1

Verdict: **changes required** (round 1).

- **MR-001 — confirmed, medium:** `src/bike_safety_ca/report/ranking.py:29–32`, `top()`. The city filter is applied only if at least one row is inside. A ranking with a known city limit and every `in_city=False` therefore returns outside-city corners, which the map and one-pager identify as the city's highest-ranked corners. Concrete case: `model rank --top 20` produces a valid ranking whose first 20 intersections all lie outside the city; supplying that CSV to `report --ranking` must not silently select them as city corners. Distinguish an absent/entirely empty city-limit field (whole-area fallback) from an explicitly false field (zero city corners). The documented absent-column fallback also currently raises AttributeError because `table.in_city` is unconditional. Add cases for all-false, all-empty and absent city flags, alongside the existing mixed case.
- **MR-002 — confirmed, medium:** `src/bike_safety_ca/report/movement_map.html:492`, `toPrint()` uses the initial `fitRisk` query flag without checking the current view. Open `?view=risk`, switch to recorded crashes, pan/zoom to another corner, then select Print this view. Printing refits the crash map to the original ranked corners instead of printing the chosen crash view. Gate the risk-only refit on the current risk view as well. Exercise the query-open → switch-back → move → print path.

Validation: read the staged diff and relevant snapshot source/tests, including the model ranking writer's city-flag schema. Executed the exact extracted `top()` control flow with minimal stand-ins: all-false returned an outside-city row and an absent flag raised AttributeError. Executed the template JavaScript with the snapshot test browser stand-in extended for layer membership and print controls: risk/crash switching and repeated print/reset passed. An isolated execution of the exact `toPrint()` function with `fitRisk=true` and current crash view confirmed it still calls `fitRanked()`. These are isolated probes, not a pandas/geospatial integration run; the implementer's reported `make check` result was not rerun. No protected files or records were opened.

Finding ledger: MR-001 open; MR-002 open. Implementer should test each finding before changing the staged files, then request round 2 with a fresh snapshot. Review does not authorize commit, push or merge.

## Handoff, round 2

- Snapshot: `/tmp/bsc-review/map-ranking-r2/`. Both findings checked against the round 1 code before fixing: `top()` used `inside.any()`, so an all-false `in_city` fell through to the whole area, and a missing column raised AttributeError; `toPrint` tested only `fitRisk`.
- MR-001: if `in_city` is present, keep only the true rows, possibly none; if it is absent, use the whole area. A new test covers both.
- MR-002: printing fits the ranked corners only when `fitRisk && risk()`. Otherwise it keeps the screen view.
- Also changed, at the user's request: printed lists stay capped, intersections at 40 and crashes at 50 (400 on screen). On paper, "zoom in to list them" becomes "and N more intersections, none with more crashes than the last one listed." or "and N more crashes in view, not listed."
- Status: ready for reviewer. Round 2 of at most 3. `make check` passed (626 tests).

## Review, round 2 — map-ranking-1

Verdict: **changes required** (round 2).

- **MR-001 — open, confirmed, medium:** `src/bike_safety_ca/report/ranking.py:30–31`. The all-false and absent-column cases are fixed, but the entirely empty column case from round 1 remains broken. The actual writer (`model/ranking.py`, `rank()`) always includes `in_city`; without a city limit it initializes that column to `pd.NA` and writes empty CSV fields. Reading that legitimate ranking gives missing values; none stringify to "true", so `top()` now returns zero corners instead of the highest-ranked corners in the whole area. Concrete case: rank an area with no city-limit outline, then pass its generated CSV to `report --ranking`: the risk switch disappears and the one-pager lists zero intersections despite a nonempty ranking. Preserve whole-area fallback when the column is entirely missing-valued, while retaining zero rows for an explicitly all-false column. Add an all-empty-column test using the writer's actual CSV representation; dropping the column does not cover this case.
- **MR-002 — closed, fixed:** `toPrint()` now checks `fitRisk && risk()`. Isolated execution confirmed a page opened on risk preserves the current crash view when printing after switching back, still refits when currently on risk, and clears print state afterward.

Reviewed the additional printed-list caps and wording against the round-2 handoff's stated user request: intersections remain capped at 40, crashes at 50 on paper versus 400 on screen, with print-specific truncation messages. No additional correctness finding in those changes.

Validation: read the round-2 staged diff, new tests, and snapshot model writer schema. Executed the exact extracted `top()` with minimal table/column stand-ins: mixed flags selected the true row; all-false selected none; absent column retained both rows; all-empty flags incorrectly selected none. Executed the exact print/reset functions in Node with controlled current-view state. Full pandas/geospatial tests were not rerun; `make check` passing 626 tests is the implementer's reported result. No protected files or records were opened.

Finding ledger: MR-001 open (partial fix; all-empty city-limit column still needs correction); MR-002 closed. Round 3 is the last round of this loop. Review does not authorize commit, push or merge.

## Handoff, round 3

- Snapshot: `/tmp/bsc-review/map-ranking-r3/`. Round 3 of 3, the last in this loop.
- MR-001 confirmed: `model/ranking.py` writes `in_city` empty without a city limit, and the round 2 filter kept no rows for it (an empty cell reads as "nan", never "true").
- Fix: `top()` filters to the city only when `in_city` has at least one value. An all-empty or missing column keeps the whole area. All-false still keeps none.
- Tests: the empty-column CSV case is written through `to_csv`, and the test checks that the file really has empty cells. The all-false and missing-column cases are kept.
- `make check` passed (626 tests). Status: ready for reviewer.

## Review, round 3 — map-ranking-1

Verdict: **accepted** (round 3, final). No new correctness findings.

- **MR-001 — closed, fixed:** `report/ranking.py`, `top()` now checks whether the city-limit column has any nonmissing value before filtering. An entirely empty column (the model writer's no-city-limit representation) and an absent column both retain the whole area; explicit all-false flags keep zero corners; mixed flags keep only true rows. The regression test now writes the empty-column case through CSV as requested.
- **MR-002 — closed, fixed:** the current-view guard remains in `toPrint()`. Printing the crash view after opening on risk preserves the chosen view; the risk view still gets its intended fit. Print cleanup clears both `inPrint` and the saved state.

Validation: reviewed the final staged changes and regression test. Executed the exact extracted `top()` with minimal table/column stand-ins for mixed, all-false, absent-column, all-NaN, all-None, and false-plus-missing flags; all six cases returned the expected ranks. Executed the exact print/reset functions in Node for both current views; both passed, including cleanup. These isolated probes do not replace a pandas/geospatial integration run. Full `make check` was not rerun; the handoff reports 626 passing tests. No protected files or records were opened.

Final ledger: MR-001 closed; MR-002 closed; no open findings. Loop map-ranking-1 is complete. The handoff's existing merge-order/rebase note for #18 still applies; review acceptance does not authorize commit, push or merge. Implementer releases the reviewer lock.

## Loop map-ranking-2: rebase onto main after #18

- Loop ID and round: `map-ranking-2`, round 1 of at most 3. Implementer: `bsc-implementer`, pane `wF:p1`. Expires (UTC): 2026-11-23 03:20.
- Base: `4f2dcd0` (main with #18 merged). Snapshot: `/tmp/bsc-review/map-ranking-rebase-r1/`; `staged.diff` is the whole change against that base.
- Purpose: the round 3 change, unchanged, rebased onto #18. #18 removed `--for`/`prepared_for` and the `warn` wrapper div.
- Conflicts resolved:
  1. `report/__main__.py`: #18's removal of `--for` kept; `--ranking`/`--top`/`--pdf` added; the map log line takes #18's wording, followed by the ranking write.
  2. `movement.py` `build()`: calls `page(..., offline=offline, ranked=ranked)`, with no `prepared_for`.
  3. `movement_map.html`: #18's bare `/*WARN*/`, with the new `id="ptitleh"` on the print title.
  4. `docs/guide.md`: #18's removal of the `--for` paragraph kept, plus the ranking paragraph.
- Checks: `make check` passed (625 tests; main's count changed with #18).
- Please check: the resolutions above, with no leftover `prepared_for` and nothing of #18 reverted.
- Status: complete (round 1 accepted)

## Review, round 1 — map-ranking-2

Verdict: **accepted** (round 1). No correctness findings in the rebase resolutions.

Reviewed the staged change against the new base, concentrating on the four named conflict resolutions. The report CLI retains #18's removal of `--for` and its log wording while forwarding `offline` and ranked markers. `movement.build()` forwards `offline` and `ranked` by keyword to the revised page signature, with no `prepared_for`. The template keeps the bare warning placeholder and adds the print-title ID without restoring the removed wrapper. The guide retains the publishing-policy wording and adds the ranking instructions. MR-001's nonmissing-city-flag check and MR-002's current-risk-view print guard remain intact; the ranking module and its regression tests retain the accepted round-3 versions.

Validation: executed the snapshot's extracted `page()` and `inline_leaflet()` functions with made-up ranking markers and minimal configuration/code-table stand-ins. All four combinations of synthetic/non-synthetic and online/offline rendering passed: only synthetic pages have the warning div, non-synthetic pages retain TIMS/CCRS credits, ranked names remain script-safe, the print-title ID is present, and offline mode embeds the vendored Leaflet assets. Checked the revised Python signatures/calls and parsed the affected Python source. These are isolated rendering checks, not a full geospatial or browser integration run. Full `make check` was not rerun; the handoff reports 625 passing tests. No protected files or records were opened.

Ledger: MR-001 closed; MR-002 closed; no new or open findings. Loop map-ranking-2 complete. Implementer releases the reviewer lock. Acceptance does not authorize commit, push or merge.
