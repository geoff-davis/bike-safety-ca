# Review: map-prints

## Current state

- Status: complete (round 2 accepted)
- Next action: none
- Base commit: `69671fa`; snapshot: `/tmp/bsc-review/map-prints-r1/`
- Open findings: none (MP-001 to MP-003 closed)
- Decisions needed from the user: none

## Loop

- Loop ID and round: `map-prints-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-prints`
- Reviewer: `bsc-reviewer` (Codex)
- Authorized scope: review requests and replies only
- Expires (UTC): `2026-11-23 19:29`

## Handoff, round 1

- Tier: Standard (a new config key plus CLI behaviour)
- Intended behavior (user's request: "make framings reproducible"): a city config's optional `prints:` list names map framings, and `report map --pdf` prints each as `<name>.pdf` in `--out`, with or without `--ranking`.
- Changes:
  - `config.py`: a new `Print` dataclass (name, at, centre, zoom, view) and a `Config.prints` tuple. `_prints` checks:
    - the entries form a list of mappings with known keys only;
    - each name matches `[a-z0-9][a-z0-9_-]*` (so no path can leave `--out`) and is unique;
    - `at` and `centre` are not both given;
    - `zoom` is present exactly when `at` or `centre` is, and is between 1 and 20;
    - `centre` is [lat, lon] within range;
    - `view` is crashes or risk.
  - `report/__main__.py`:
    - `framing_url` builds `file://…/crash_movement_map.html[?view=risk][#lat,lon,zoom]`. An `at` is resolved from the page's own `const SITES=` JSON (`raw_decode` from that offset), and anything other than exactly one match is an error.
    - `print_framings` resolves every URL first, so a bad name prints nothing, then prints each through `pdf.print_url` with a 15 s budget.
    - These run in the map step when `--pdf` is set and the config has prints.
  - Configs: the framings of the existing hand-printed PDFs. Los Altos: the opening view plus five corners by name at z18. San Francisco: city z12 and downtown z14 by centre. Mountain View and Palo Alto: city z13 by centre.
  - `docs/guide.md` documents the key.
- Verification:
  - New tests: config acceptance plus eleven refusal cases (including `../city`); the CLI test with Chrome faked covers an opening view, `at`, a risk centre, file names, and a missing name stopping the run before any print.
  - `make check` passed (644 tests).
  - Real runs, Los Altos and San Francisco: every PDF from the configs shows the same crashes in view and the same zoom as the hand prints.
- Condition inventory:

  | Condition | Test or probe | Result |
  | --- | --- | --- |
  | no prints key | existing configs and tests | caught |
  | name path traversal | `../city` refusal | caught |
  | at not found | CLI test | caught |
  | at matching two sites | not exercised (same error path, count 2) | not exercised |
  | view risk with no ranking | not exercised: the page ignores ?view=risk with no ranked corners and prints the crash view | not exercised |

- Known limitations: `at` only finds intersections with a recorded crash, because the page's SITES are crash sites. A `view: risk` framing on a map with no ranked corners prints the crash view; risk framings are meant for ranked runs.

## Review, round 1 — map-prints-1

Verdict: **changes required** (round 1).

- **MP-001 — confirmed, medium:** `report/__main__.py`, `framing_url()` risk URL construction, interacting with `movement_map.html` risk startup and `toPrint()`. The produced risk URL carries the requested hash, but the template immediately calls `fitRanked()` for any nonempty ranking and `?view=risk`, then calls it again when printing. Concrete case: `{name: risk-north, centre: [37.40, -122.11], zoom: 15, view: risk}` with ranked corners elsewhere opens/prints the all-ranked-corners fit instead of the configured centre/zoom. This breaks the new reproducible risk framing even with valid ranking data. Preserve explicit hash framing through both risk startup and print layout; keep automatic ranked fitting for the unframed risk URL. Add a behavioral test of the resulting map/print state, rather than only asserting the URL string.
- **MP-002 — confirmed, medium:** `report/__main__.py`, `print_framings()` accepts risk framings without checking whether the generated map supports risk mode. With no ranking (or an empty in-city ranking), the page ignores `?view=risk` and prints recorded crashes under the configured risk filename. Example: the documented `risk-north` framing followed by `report map --pdf` without `--ranking` silently produces a crash PDF. The earlier automatic predicted-risk print correctly guards this situation, but the new path bypasses that guard. Reject the unavailable risk framing or skip it with an explicit warning, or implement an actual empty/list-free risk view. Add no-ranking and empty-ranking framing tests. This is the known limitation recorded in the handoff, but it conflicts with the new `view: risk` behavior and needs explicit handling.
- **MP-003 — confirmed, medium:** `config.py`, `_prints()` name validation, and the CLI's automatic/configured output paths. The names `predicted_risk` and `top_corners` pass validation and collide with the automatic ranking PDFs. With `prints: [{name: predicted_risk}, {name: top_corners}]` and `--ranking ... --pdf`, the ordinary crash framing overwrites the predicted-risk PDF, and the automatic one-pager subsequently overwrites the `top_corners` map framing. Validate these collisions before printing (for example, reserve the automatic names, or compute a collision-free output plan). Add regression coverage that both requested output types cannot silently target one file.

Validation: executed the exact `_prints()` and `framing_url()` functions on made-up inputs. Valid risk-north config produced the documented risk query/hash, and both automatic PDF names were accepted. Executed the template's exact hash initialization/risk-fit code in Node with controlled map stand-ins: a nonempty ranking overwrote the requested framing with the ranked fit; no ranking kept the framing but stayed in crash view. Executed the exact CLI `main()`/framing helpers with inert I/O/printer stand-ins for the name-collision case: four writes targeted only two PDF paths, with different content for each repeated target. Reviewed parser constraints, site JSON lookup, staged tests and print ordering. Full geospatial/browser/PDF integration and `make check` were not rerun; the handoff reports 644 passing tests. No protected files or records were opened.

Finding ledger: MP-001 open; MP-002 open; MP-003 open. Test each finding before changing staged files, then request round 2 with a fresh snapshot. Implementer releases the reviewer lock. Review does not authorize commit, push or merge.

## Handoff, round 2

- Snapshot: `/tmp/bsc-review/map-prints-r2/`. Round 2 of at most 3.
- MP-001 (risk refit overrode the address's framing):
  - New Node test `test_the_risk_view_keeps_a_framing_given_in_the_address` (framed and opening cases). It is written against the page script with a stub `fitBounds` and checks the opening fit count, the print decision and the zoom.
  - On round 1's template the framed case fit on opening (and has no `refit`).
  - Fix: `HASHED` (the address gave #lat,lon,zoom) and `refit()=fitRisk&&!HASHED&&risk()`, used both at startup and in `toPrint`. `?view=risk` alone still frames the ranked corners.
  - Real run: a Los Altos `view: risk` framing at zoom 15 printed the risk view at zoom 15, while the automatic predicted_risk.pdf stayed fitted (12.25).
- MP-002 (risk framing with no ranked corners): `print_framings(..., ranked)` raises before any print when a risk framing meets a map with no ranked corners (no `--ranking`, or none in the city). The CLI test runs a risk framing without `--ranking` and expects the error, with nothing printed.
- MP-003 (names colliding with automatic PDFs): `MADE_BY_PDF = {predicted_risk, top_corners}`; these names are refused in config with "made by --pdf itself", and two refusal cases were added.
- The MP-002 and MP-003 tests were written before their fixes, but I did not record their failing runs separately; MP-001's failure on the old template was observed.
- Checks: `make check` passed (648 tests).

## Review, round 2 — map-prints-1

Verdict: **accepted** (round 2). No new blocking correctness findings.

- **MP-001 — closed, fixed:** `HASHED` records the initial address framing, and `refit()` excludes that case both at startup and in `toPrint()`. The default risk URL still fits ranked corners. The new Node test covers framed versus opening behavior.
- **MP-002 — closed, fixed:** `print_framings()` validates risk availability for every configured framing before resolving/printing its batch. Both absent ranking and empty in-city ranking yield the CLI's `ranked=False`, so neither silently prints a crash map as a risk framing.
- **MP-003 — closed, fixed:** config loading reserves `predicted_risk` and `top_corners` before execution, preventing configured outputs from colliding with automatic ranking PDFs. Both refusals have regression cases.

Validation: executed the exact hash initialization, risk startup, `toPrint()` and `fromPrint()` code in Node with controlled map stand-ins. Explicit [37.4, -122.11], zoom 15 stayed unchanged on opening and printing with zero automatic fits; the unframed risk URL fit once on opening and again for print. Print cleanup passed. Executed the exact config parser: both reserved names raised the intended ValueError. Executed the exact framing helpers with inert printer: a batch containing crash and risk framings with ranked=False raised before any configured print call; ranked=True printed both URLs, including the requested risk hash. Reviewed revised tests and CLI propagation of the availability flag. These are isolated checks, not full browser/geospatial/PDF integration tests. Full `make check` was not rerun; the handoff reports 648 passing tests. No protected files or records were opened.

Final ledger: MP-001 closed; MP-002 closed; MP-003 closed; no open findings. Loop map-prints-1 complete. Implementer releases the reviewer lock. Acceptance does not authorize commit, push or merge.
