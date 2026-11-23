# Review: banner-wording

## Current state

- Status: complete (accepted in round 2)
- Next action: none
- Base commit: `1b253e8`; snapshot: `/tmp/bsc-review/banner-wording-r1/`
- Open findings: none
- Decisions needed from the user: none

## Loop

- Loop ID and round: `banner-wording-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-banner`
- Reviewer: `bsc-reviewer` (Codex)
- Authorized scope: review requests and replies only
- Expires (UTC): 2026-11-23 01:04

## Handoff, round 1

- Tier: Small
- Purpose: the user asked to tone down the crash map's banner. It read "Confidential: individual police records. Do not publish or pass on.", which sounds like a legal condition. Neither source imposes one: TIMS's terms ask only for credit, and CCRS is public domain on data.ca.gov. `docs/guide.md` "Crash records" already says keeping records private is this repository's own rule.
- New banners (`report/movement.py`):
  - with `--for`: "Prepared for {who}. Shows individual crash records (TIMS, CCRS). Please do not publish it.";
  - without it: "Shows individual crash records (TIMS, CCRS). Please share it privately and do not publish it."
- Also changed to match: the module docstring, the log line in `report/__main__.py`, and two guide paragraphs (the `--for` description and the note after it).
- The demo's synthetic banner is unchanged, so `docs/demo/` is not rebuilt.
- Tests: the two banner assertions in `tests/test_report.py` now check the new text. `make check` passed (621 tests).
- Please check:
  - that the guide still agrees with "Crash records" and the README;
  - that no other place still states the old wording.

## Review, round 1 — bsc-reviewer

- Loop: `banner-wording-1`, round 1.
- Reviewed `/tmp/bsc-review/banner-wording-r1/staged.diff`, changed notices,
  rendering branch and assertions, report command/log, guide's map and
  Crash-records sections, README privacy section and notebook notices.
- Verified lock ownership (`bsc-implementer banner-wording`), `HERDR_ENV=1`,
  and requesting Claude identity, repository and pane `wF:p1` through Herdr.
- Changed text: the new guide/map banner and log agree with the README and
  the guide's existing instruction to share record-level output privately
  with local-authority staff. The supplied purpose is implemented without
  removing the no-publication request. This review checks repository
  consistency, not the underlying legal/source-terms claims independently.
- Checks: parsed touched Python files; evaluated the exact notice constants,
  recipient formatting and HTML escaping with a made-up recipient containing
  angle brackets and ampersand. Escaping remains correct. The synthetic
  notice and the synthetic-override rendering branch are unchanged.
- Searched for obsolete user-facing sharing language. Evaluated the exact
  notebook `_privacy` AST expression for `config.synthetic=False`, which
  returns the old “Do not share or publish it” wording (BW-001). The map
  cell inserts that value into its displayed Markdown beside the generated
  map link; no real records or notebook execution were needed for the probe.
- Evidence reused: implementer's reported 621-test `make check`. Did not
  rerun the suite or render the notebook in a browser; no protected data
  paths opened.
- Verdict: **changes required, round 1**, for BW-001. No other correctness
  findings. A verdict authorizes no commit, push or merge.

### BW-001 — P2, blocking, confirmed: notebook retains the contradictory sharing ban

- Location: snapshot `notebooks/walkthrough.py:484`; related opening notice
  at lines 147–149.
- Concrete failing case: choose a real-data city in the walkthrough and
  open section 8. The map cell calls the changed `movement.build`, whose
  banner now permits private sharing, but displays “The map shows individual
  police records. Do not share or publish it.” immediately beside the map
  link. The opening real-record notice also says “share totals only.”
- Confirmed by evaluating the exact conditional expression with a synthetic
  config object whose `synthetic` property is false, and inspecting its
  insertion into the displayed `mo.md` text. The synthetic branch remains
  appropriately separate.
- Impact: notebook users still see the old blanket prohibition for the same
  map whose banner has been softened, failing the requested check that no
  other user-facing place retains the old wording.
- Required correction: align both notebook real-record notices with private
  sharing to local-authority staff and no publication. Preserve the
  synthetic notices. The remaining historical “keep on your own computer”
  reference in `movement.page`'s docstring can also be updated while touching
  this wording; it is not a separate blocking finding.
- Status: open.

## Finding ledger, round 1

| ID | Severity | Blocking | Location | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| BW-001 | P2 | Yes | `notebooks/walkthrough.py:484` | open | Exact real-data branch still returns blanket no-sharing text beside the map; opening notice says share totals only. |

## Handoff, round 2

- Snapshot: `/tmp/bsc-review/banner-wording-r2/`. Loop `banner-wording-1`, round 2 of 3. Expires (UTC): 2026-11-23 01:07.
- BW-001 fixed in `notebooks/walkthrough.py`, real-data branches only (the synthetic text is unchanged):
  - the opening notice now says "Real crash records for {city}. The tables and the map below include individual crashes. Share them privately, with the local authority's staff, rather than publish them; tables of totals can be published with the sources' credits.";
  - the section 8 note now says "The map shows individual crash records. Share it privately; please do not publish it."
- Also aligned: the `report/__init__.py` docstring and the `report/__main__.py` docstring, which is the command's `--help` text.
- Left alone, on purpose:
  - `download/ccrs.py` and `crashes/tims.py` ("keep the folder out of version control"): about the raw tables, not the map;
  - the guide's "Crash records" opening, which already explains that the rule is the repository's own.
- `make check` passed (621 tests).

## Review, round 2 — bsc-reviewer

- Loop: `banner-wording-1`, round 2.
- Reviewed `/tmp/bsc-review/banner-wording-r2/staged.diff`, both revised
  notebook notices and aligned package/CLI documentation. Reused round 1's
  banner rendering, recipient escaping and guide/README consistency review.
- Verified lock ownership (`bsc-implementer banner-wording`), `HERDR_ENV=1`,
  and requesting Claude identity, repository and pane `wF:p1` through Herdr.
- BW-001: fixed. The opening notebook notice now directs private sharing
  with local-authority staff and distinguishes publishable credited totals;
  section 8's map note permits private sharing and requests no publication.
  Package and command-help docstrings use the same distinction.
- Independent checks: evaluated the exact `_privacy` conditional expression
  for real and synthetic configurations, plus the opening real-data
  formatted string using a made-up city. Real notices contain the revised
  sharing language; the synthetic map notice is unchanged. All touched
  Python files parse. A targeted search over report source, notebook,
  README, guide and report tests found no remaining old blanket no-sharing
  phrases (rg exit 1 signifies no matches).
- Evidence reused: implementer's reported round-2 `make check` success
  (621 tests). No full suite, browser rendering, legal/source-terms check or
  protected-data access performed; round 1's limits continue to apply.
- Findings: no new correctness findings.
- Verdict: **accepted, round 2**. BW-001 is fixed in the staged snapshot.
  This completes the review loop; acceptance authorizes no commit, push or
  merge.

## Finding ledger, round 2

| ID | Severity | Blocking | Status | Evidence |
| --- | --- | --- | --- | --- |
| BW-001 | P2 | Resolved | fixed | Both real-data notebook notices aligned; exact-expression probes pass and obsolete blanket no-sharing wording is absent from the reviewed source/docs. |
