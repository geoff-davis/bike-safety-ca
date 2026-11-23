# Review: report-links

## Current state

- Status: complete (round 1 accepted)
- Next action: none
- Base commit: `2a5c8bb`; snapshot: `/tmp/bsc-review/report-links-r1/`
- Open findings: none
- Decisions needed from the user: none

## Loop

- Loop ID and round: `report-links-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-links`
- Reviewer: `bsc-reviewer` (Codex)
- Authorized scope: review requests and replies only
- Expires (UTC): `2026-11-23 18:53`

## Handoff, round 1

- Tier: Small
- Intended behavior (user's request): the reports link to the GitHub repository (public; checked), and the predicted-risk view links to the model details (`docs/forecasting_model.md`).
- Changes:
  - New `bike_safety_ca/links.py`: `REPO`, `doc(name)`, `MODEL_DOC`, `SHOWN` and the `MADE_WITH` Markdown line.
  - Hospital county and e-bike reports: `MADE_WITH` closes the text. The county report's "docs/county_rates_method.md of bike-safety-ca" becomes a link.
  - `ranking.markdown` (top_corners): a line linking the model page, with its address shown in full, and `MADE_WITH`.
  - Map template: new `/*REPO*/` and `/*MODEL_DOC*/` fills (constants, not user input).
    - The print header credit adds "Made with bike-safety-ca" plus a linked address.
    - The Leaflet attribution adds a link.
    - The risk view's screen note and key get a "How the model works" link (`target=_blank rel=noopener`).
    - The printed risk key (`RISKKEY`) writes the model address as text.
  - The synthetic demo map gets the same links.
- Verification:
  - New assertions in `test_report_ranking.py` (one-pager and both map pages, no unfilled markers) and `test_hospital_report.py` (both reports). `make check` passed (632 tests).
  - Real builds: `pdfinfo -url` shows the repo and model links in top_corners.pdf, the repo link in predicted_risk.pdf, and the repo and method links in the made-up hospital sample PDF. A screenshot shows the links in the panel, key and attribution.
- Settled decisions: links point at `main` on GitHub. The printed address is written out because paper cannot be clicked.

## Review, round 1 — report-links-1

Verdict: **accepted** (round 1). No correctness findings.

Reviewed the shared link constants, hospital report additions, one-pager links and template substitutions. The two document paths match files in the snapshot. The new template fills use fixed URLs, preserve single-pass replacement and script-safe data handling, and produce the intended repository credit and model links. The printed model address is plain text as specified in the handoff; screen links retain target/rel attributes. The hospital reports append the shared Markdown credit and the county method link without changing calculations.

Validation: executed the snapshot `links.py`, extracted `page()`/`inline_leaflet()` and one-pager Markdown functions with made-up data and minimal dependency stand-ins. All four map combinations (synthetic/non-synthetic, online/offline) contained both expected URLs, had no unfilled link placeholders, preserved escaping and passed Node JavaScript syntax checking. The one-pager emitted both Markdown links. Reviewed the new hospital/report assertions. Full report/PDF integration and `make check` were not rerun; the handoff reports 632 passing tests and PDF URL checks. Remote GitHub availability was not independently checked, keeping this review snapshot-only. No protected files or records were opened.

Ledger: no open findings. Loop report-links-1 complete. Implementer releases the reviewer lock. Acceptance does not authorize commit, push or merge.
