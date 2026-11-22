# Review: report-tips

## Current state

- Status: complete (accepted in round 1)
- Next action: none
- Base commit: `9f97f98`; snapshot: `/tmp/bsc-review/report-tips-r1/`
- Open findings: none
- Decisions needed from the user: none

## Loop

- Loop ID and round: `report-tips-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-report-tips`
- Reviewer: `bsc-reviewer` (Codex)
- Authorized scope: review requests and replies only
- Expires (UTC): 2026-11-22 22:49

## Handoff, round 1

- Tier: Medium
- Purpose: the user asked that the jargon on the reports have tooltips with definitions, like walkbike-routes'. The crash movement map (`report/movement_map.html`) is the only HTML report; the hospital report is Markdown or PDF. Mechanism copied from walkbike-routes: `<span tabindex="0" data-tip="...">` with a dotted underline, one fixed `#tip` box, and show/hide on mouseover/focusin, hide on mouseout/focusout/scroll. Print hides the box and the underline.
- Definitions live once, in `TIPS`, `SEVTIP` and `COLLTIP` in the page script, with a `tip(html, def)` helper. Static labels (school commute hours, Other party, Wrong side, after dark) carry `data-term` and get their text from `TIPS` on load.
- Marked: the filters; in the popups, at fault, cause coded, the collision type and the severity; in the panel, Diagram check, Repeated patterns, the Streets-in-view column heads, the Severity/light and Pattern heads and the severity values; in the key, Worst injury and its values, Movement before the crash, and collision diagrams.
- Definitions follow the code: commute is `school_commute` in `report/crashes.py` (hours 7–8 and 14–16, so 7:00–8:59 and 2:00–4:59); dark is `codes.DARK`; wrong side is `wrong_side_coded` in `report/movement.py`.
- The tooltip code is at the end of the one page script, and `#tip` sits just before it, because `test_movement_page` runs the page's last `<script>`. Its stand-in `document` gains `querySelectorAll` and `addEventListener`.
- `docs/demo/crash_movement_map.html` (the GitHub Pages demo, made-up data) was rebuilt with `--offline`. Its diff from the old copy is only the template change.
- Tests: new `tests/test_map_terms.py` checks that every TIPS key used is defined and every defined key is used, and that the box, script and print rule are on the page. Headless Chrome on the demo: 15 marked terms on the opening view, all 15 show their own text on hover; focus shows it too; no script errors. Popups built for every demo crash carry tips for at fault, cause coded, collision types and severities.
- `make check` passed (604 tests).
- Please check: the wording of the definitions against the code (above all commute hours, wrong side and serious injury), escaping (`esc` on `data-tip`; tip text set via `textContent`), print behaviour, and anything the tooltips break in the map (popups, the legend control, the panel's click handling).

## Review, round 1 — bsc-reviewer

- Loop: `report-tips-1`, round 1.
- Reviewed `/tmp/bsc-review/report-tips-r1/staged.diff`, template changes,
  synthetic demo tooltip code, added/adjusted tests and relevant commute,
  wrong-side, severity, collision and lighting code.
- Verified lock ownership (`bsc-implementer report-tips`), `HERDR_ENV=1`,
  and requesting Claude identity, repository and pane `wF:p1` through Herdr.
- Definitions: commute hours match inclusive integer hours 7–8 and 14–16,
  weekdays and configured summer exclusion; the caveat about other holidays
  is retained. Darkness matches C/D/E and excludes dusk/dawn. Coded wrong
  side distinguishes the cyclist's own wrong-way movement and a cyclist
  marked at fault for the wrong-side cause; serious totals use severities
  1/2. New tooltip spans retain the visible labels and surrounding handlers.
- Escaping/print: `esc` escapes definitions in double-quoted data attributes;
  popup values remain escaped before being passed as HTML labels. Tooltip
  text uses `textContent`. Print CSS hides the shared tooltip and removes
  data-tip borders; the existing print view logic remains unchanged.
- Independent Node probe executed the exact template glossary/helper and
  event IIFE with a minimal DOM stand-in: static term initialization,
  keyboard tab stop, delegated mouseover/focusin, mouseout/focusout/scroll
  hiding, horizontal bounds positioning and a made-up definition containing
  angle brackets, ampersand and quotes all passed.
- Verified the generated synthetic demo's glossary/helper and tooltip IIFE
  exactly match the template. All 14 TIPS keys are both defined and used;
  changed Python test files parse. Inspection found no new click listener
  or event suppression that changes pattern picking, popup or legend logic.
- Evidence reused: implementer's reported 604-test `make check`, headless
  Chrome hover/focus checks, no-script-error result and all-demo-popup check.
- Limits: no independent browser rendering, print-preview or full-suite run;
  Node stand-ins do not verify real layout or event interactions in Leaflet.
  Injury-category examples were not independently checked against external
  clinical/coding references. No real crash records or protected data paths
  opened.
- Findings: none.
- Verdict: **accepted, round 1**. This completes the review loop; acceptance
  authorizes no commit, push or merge.
