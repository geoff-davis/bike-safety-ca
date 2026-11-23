# Review: risk-pdf

## Current state

- Status: complete (round 2 accepted)
- Next action: none
- Base commit: `2ec147d`; snapshot: `/tmp/bsc-review/risk-pdf-r1/`
- Open findings: none
- Decisions needed from the user: none

## Loop

- Loop ID and round: `risk-pdf-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-risk-pdf`
- Reviewer: `bsc-reviewer` (Codex)
- Authorized scope: review requests and replies only
- Expires (UTC): `2026-11-23 07:57`

## Handoff, round 1

- Tier: Small
- Intended behavior (user's request): the predicted-risk PDF (the map's risk view with its list of corners), so far printed by hand in headless Chrome, is generated along with the rest. `report map --ranking X --pdf` now writes `predicted_risk.pdf` beside `top_corners.pdf`.
- Changed areas:
  - `hospital/pdf.py`: the new `print_url(url, target, wait_ms=0)` holds the Chrome call. Each print gets a fresh temporary `--user-data-dir` (one Chrome locks a profile, which broke manual prints while another Chrome ran), plus `--no-first-run`, `stdin=DEVNULL`, an optional `--virtual-time-budget`, and a 300 s timeout (was 120). `write` (the hospital reports and top_corners) now calls it; the arguments are otherwise unchanged.
  - `report/__main__.py`: in the map step, when a ranking and `--pdf` are both given, print `<map>.resolve().as_uri() + "?view=risk"` with a 15 s virtual-time budget to `predicted_risk.pdf`. The `--pdf` help text is updated.
  - `docs/guide.md`: the risk view is described as circles, and `--pdf` now names both PDFs.
- Verification:
  - New test `test_the_report_command_prints_the_risk_view_and_the_corners`: Chrome is faked through `pdf.shutil.which` and `pdf.subprocess.run`. It checks both PDFs, the `?view=risk` URL with the budget, a separate profile per print, and no print without `--pdf` or without `--ranking`.
  - `make check` passed (632 tests).
  - A real run with real Chrome on a city build wrote `predicted_risk.pdf`, matching the hand print: same page count and table, no screen-only note.
- Settled decisions: printing stays behind `--pdf` (Chrome is optional). The risk print is made only when the map step runs. The 15 s budget is the value used for the hand prints.
- Known limitations: the print waits on virtual time and does not detect that the map has finished drawing.

## Review, round 1 — risk-pdf-1

Verdict: **changes required** (round 1).

- **RPDF-001 — confirmed, medium:** `src/bike_safety_ca/report/__main__.py:102–106`, new risk PDF print branch. `top is not None` is true for an empty ranking result, but `movement_map.html` enters risk mode from the query only when `RANKED.length > 0`. Consequently the command writes `predicted_risk.pdf` containing the recorded-crash map, title and key instead of the requested risk view. Concrete case: supply a valid ranking CSV whose `in_city` flags are all false (for example, a truncated area ranking with no city corner), then run `report map --ranking ... --pdf`. The supported `--top 0` case also reaches this mismatch, potentially despite available expected-count circles. Either print a real empty/list-free risk view or explicitly skip/reject risk PDF generation when that view is unavailable; do not silently label a recorded-crash print as predicted risk. Add regression coverage for an empty `top` result.

Validation: executed the exact new CLI print branch with an empty top result and an inert printer; it still requested `predicted_risk.pdf` with `?view=risk`. Executed the exact query-selection and print functions in Node with that empty ranked list: the selected view stayed `crashes`, the printed title was `Cyclist crashes, Example`, and the crash key was used. Executed the exact `print_url()` with inert temporary-profile and subprocess stand-ins: distinct profiles, optional 15000 ms virtual-time flag, absent flag for the default budget, DEVNULL stdin, check=True and the 300 s timeout passed. Reviewed `write()` delegation, CLI gating and the new fake-Chrome test. These are isolated control-flow checks, not live Chrome/PDF integration tests. Full `make check` was not rerun; the handoff reports 632 passing tests. No protected files or records were opened.

Finding ledger: RPDF-001 open. Test the finding before changing staged files, then request round 2 with a fresh snapshot. Implementer releases the reviewer lock. Review does not authorize commit, push or merge.

## Handoff, round 2

- Snapshot: `/tmp/bsc-review/risk-pdf-r2/`. Round 2 of at most 3.
- RPDF-001 confirmed before fixing: the test now reruns with `--top 0` after deleting the first `predicted_risk.pdf`, and on round 1 it failed because the file was printed again (recorded-crash view).
- Fix: when `top` is empty, the risk print is skipped and a warning says so (`no ranked corner in the city: predicted_risk.pdf not printed`). An empty top comes from `--top 0` or no in-city rows, both through `ranking.top`. `top_corners.md`/`.pdf` are written as before.
- Known limitation: a `predicted_risk.pdf` left in the output folder by an earlier run is not removed.
- Checks: the test asserts no file and no `?view=risk` print. `make check` passed (632 tests).

## Review, round 2 — risk-pdf-1

Verdict: **accepted** (round 2). No new correctness findings.

**RPDF-001 — closed, fixed:** the risk PDF branch checks `top.empty` and explicitly warns/skips printing when the page cannot enter risk view. A nonempty ranking still prints the risk query with the 15-second budget. The corner report remains independently generated. The regression test now exercises `--top 0`, verifies no risk print call and no newly produced risk PDF, and retains the populated-ranking and disabled-option checks.

Validation: executed the exact extracted risk-print and corner-write branches with inert printer/report stand-ins for empty ranking, populated ranking, no ranking, and PDF disabled. The empty case made no risk print call, emitted one warning and continued the corner report; only the populated PDF-enabled case printed the risk URL, with the expected budget. Reviewed the staged diff and regression assertions. Full Chrome/PDF integration and `make check` were not rerun; the handoff reports 632 passing tests. No protected files or records were opened.

The documented limitations remain: print completion uses a virtual-time budget rather than map readiness, and skipping a risk print leaves any PDF from an earlier run untouched. Neither was changed by this fix.

Final ledger: RPDF-001 closed; no open findings. Loop risk-pdf-1 complete. Implementer releases the reviewer lock. Acceptance does not authorize commit, push or merge.
