# Review: risk-colour

## Current state

- Status: complete (round 1 accepted)
- Next action: none
- Base commit: `8f11e5a`; snapshot: `/tmp/bsc-review/risk-colour-r1/`
- Open findings: none
- Decisions needed from the user: none

## Loop

- Loop ID and round: `risk-colour-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-risk-colour`
- Reviewer: `bsc-reviewer` (Codex)
- Authorized scope: review requests and replies only
- Expires (UTC): `2026-11-23 17:50`

## Handoff, round 1

- Tier: Small (one template, `src/bike_safety_ca/report/movement_map.html`)
- Intended behavior (the user's requests, after seeing previews):
  1. Risk circles show expected crashes by colour as well as size. `riskT(e)` maps sqrt(e) linearly from 0 at the 0.5 floor to 1 at CMAX, clamped, and is 1 when CMAX <= 0.5. `riskCol` interpolates a four-stop yellow, orange, red, dark-red ramp. Fill opacity is 0.75. Circles are drawn largest first, so small ones stay on top. Ranked corners have a #222 outline, as do ranked corners with no circle. The unused `RISKC` is removed.
  2. The on-screen key follows the view. `legend()` keys its cache on `"risk"` or the zoom level and, in risk view, draws `riskLegend()`: reference sizes from `riskSizes()` (0.5 plus up to three within [CMAX/10, CMAX]), the floor note, the ranked-outline sample, and a hint. The view-change handler calls `legend()`. The print key (`RISKKEY`/`circleKey`) uses the same sizes.
  3. In the recorded-crash view, the "Intersections, most crashes first" list (zoom level 0) links each name. Rows carry `data-si`, and `listed` holds that list's site-to-crashes map from the latest draw. A delegated click opens `sitePopup(SITE[i], listed[i])` in a standalone `L_.popup` with `autoPan:false` and does nothing in risk view. The list holds intersections in view, so a pan or zoom would change it under the pointer. The risk list's names are styled as links too (`a.go`, plain on paper), with `preventDefault` added.
- Verification:
  - `make check` passed.
  - Headless Chrome on real builds (counts and street names only):
    - the key switches risk, crashes, risk with no errors;
    - in San Francisco, clicking each of the first six crash-list links opened the matching popup;
    - the list is unchanged before and after a click (same centre and zoom);
    - the prints show yellow at 0.5 and the risk key.
- Settled decisions: colour is per city, like size. Red reuses a hue from the crash view's severity colours; the user saw this and kept it.
- Known limitations: near the top edge the crash-list popup can be clipped (no autoPan, by design). Pale yellow circles are faint on the built-in map's yellow major roads.

## Review, round 1 — risk-colour-1

Verdict: **accepted** (round 1). No blocking correctness findings.

Reviewed the colour normalization/interpolation, largest-first circle rendering, shared key samples, view-aware legend cache and delegated crash-list links. The colour endpoints and the explicit CMAX <= 0.5 branch avoid division by zero. Rendering sorts a copy of the circles. `listed` is refreshed with the displayed city-level intersection list, and its click handler uses those rows for the popup with autoPan disabled. The risk and recorded-crash handlers distinguish their row attributes and view; default link navigation is prevented. Legend caching now distinguishes risk mode from each recorded-crash zoom level.

Validation: executed the full snapshot template script in Node using the snapshot browser/Leaflet stand-in extended for popup and layer operations, with made-up crashes at two intersections. Ran three scenarios: no expected circles, maximum 0.5, and maximum 20. In every scenario both crash-list links opened their matching popups with autoPan=false and left the map-view call count and panel contents unchanged; risk → crashes → risk switches produced the correct key each time; generated colours were valid; endpoint normalization and descending circle paint order passed. Reviewed screen/print link styling and the shared circle-key implementation. These are stand-in browser checks, not live Chrome or PDF rendering tests. Full `make check` was not rerun; the handoff reports it passed. No protected files or records were opened.

Ledger: no open findings. Loop risk-colour-1 complete. Implementer releases the reviewer lock. Acceptance does not authorize commit, push or merge.
