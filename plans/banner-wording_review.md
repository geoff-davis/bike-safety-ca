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

## Loop 2: publishing policy

- Loop ID and round: `banner-wording-2`, round 1 of at most 3. Base: `59c43e5` (round-2-accepted commit 59c43e5). Snapshot: `/tmp/bsc-review/banner-wording-2-r1/`. Expires (UTC): 2026-11-23 01:56.
- Implementer: `bsc-implementer`, pane `wF:p1`. Reviewer: `bsc-reviewer`.
- Purpose: the user decided, after reading both sources' terms, that the "keep record-level output private" rule goes. The decisions:
  1. maps and reports of single crashes may be published with the TIMS and CCRS credits; record tables stay out of the repository, and tests stay on made-up data;
  2. the map's banner goes for real records, along with `--for`;
  3. (a session rule for the implementer, not in the diff);
  4. the reviewer's own limits in `AGENTS.md` ("What the reviewer may see") are unchanged.
- Code:
  - `movement.page` and `build` lose `prepared_for`, and `PREPARED_FOR` is gone;
  - `REAL_NOTICE` becomes `REAL_CREDIT`;
  - the template's `/*WARN*/` is now filled with the whole `<div class="warn">`, or with nothing for real records; the demo keeps its synthetic banner, and the demo page is byte-identical apart from a trailing newline that predates this change;
  - `--for` is removed from `report`; the log line is just "wrote …".
- Text: `AGENTS.md` Data, the README's "Crash records" section (renamed from "Keeping records private", with its link fixed), the guide's "Crash records" section and map paragraphs, the walkthrough notebook's real-data notices, and the report docstrings.
- Tests: the `--for` test is removed, and the three banner checks now assert that there is no banner on real records and that the credit is there. `make check` passed (620 tests).
- Please check:
  - that no other place still tells users to keep record-level output private, or mentions `--for`;
  - that the guide's terms summary is unchanged in substance;
  - that removing `prepared_for` leaves no caller behind.

## Review — banner-wording-2, round 1 — bsc-reviewer

- Reviewed `/tmp/bsc-review/banner-wording-2-r1/staged.diff`, banner
  construction, template, CLI removal and callers, notebook notices,
  README/guide policy wording and the AGENTS change.
- Verified lock ownership (`bsc-implementer banner-wording`), `HERDR_ENV=1`,
  and requesting Claude identity, repository and pane `wF:p1` through Herdr.
- Code checks: no remaining `prepared_for`, `PREPARED_FOR`, `REAL_NOTICE`,
  `--for` or old README anchor references found in the searched live source,
  tests, notebook, README and guide. The internal build-to-page call now
  passes `offline` by keyword, avoiding positional confusion after the
  parameter removal. Credits remain in the map attribution and print title.
- Independent rendering probe: executed the exact snapshot `page` function
  extracted through AST, with template-resource and config stand-ins, empty
  made-up rows and the snapshot's actual code dictionaries. Real output
  has credits and no warning div; synthetic output has its warning and
  synthetic credits. City-name HTML escaping still works.
- Policy checks: the source-specific TIMS/CCRS terms bullets and existing
  litigation/use-limit discussion remain substantively unchanged in the
  diff. The new publication permission reflects the user decision described
  in this handoff; source terms and legal interpretation were not independently
  revalidated. The AGENTS reviewer-access rules are unchanged.
- Searched for prior publication restrictions. One obsolete notebook
  instruction remains (BW-002); evaluated its exact closing Markdown
  expression with made-up config/path values to confirm it is displayed.
- Evidence reused: implementer's reported 620-test `make check`. No full
  suite or browser/print rendering run; no protected records or paths opened.
- Verdict: **changes required, banner-wording-2 round 1**, for BW-002.
  No other correctness findings. A verdict authorizes no commit, push or merge.

### BW-002 — P2, blocking, confirmed: closing notebook instructions retain the withdrawn policy

- Location: snapshot `notebooks/walkthrough.py:537–539`.
- Section 9 still displays: “Keep the tables, the ranking's crash counts for
  single corners and the movement map on your own computer, and publish
  totals.” This paragraph is unconditional, so a user following the notebook
  for a real city reads it after the newly updated permission to publish
  maps and reports with credits.
- Concrete probe: evaluating the exact closing Markdown AST expression with
  made-up `config_path` and `_folder` values reproduces that paragraph.
  It still expressly includes the movement map and per-corner ranking
  output among the things to keep on the user's computer.
- Impact: contradicts the new publication policy and fails the handoff's
  requested check for remaining instructions to keep record-level output
  private. Keeping source record tables out of the repository is a separate
  rule and need not be removed.
- Required correction: update this closing paragraph to distinguish source
  record tables from publishable credited maps/reports, consistent with the
  README and guide. No need to restore a real-data banner or `--for`.
- Status: open. BW-001 from the earlier loop remains fixed; this finding
  concerns the new policy's broader scope.

## Finding ledger — banner-wording-2, round 1

| ID | Severity | Blocking | Location | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| BW-002 | P2 | Yes | `notebooks/walkthrough.py:537` | open | Exact closing Markdown still directs keeping maps and per-corner outputs on the user's computer while publishing totals. |

### Loop 2, handoff round 2

- Snapshot: `/tmp/bsc-review/banner-wording-2-r2/`. Loop `banner-wording-2`, round 2 of 3. Expires (UTC): 2026-11-23 01:59.
- BW-002 fixed: the closing paragraph of `notebooks/walkthrough.py` now says "Police crash records describe real people. The record tables stay out of version control; get them from TIMS and CCRS. The ranking, the movement map and its PDFs can be shared or published with the TIMS and CCRS credits."
- A repo-wide search for "own computer", "totals only", "publish totals", "privately" and "keep … private" in `.py` and `.md` files (outside `plans/` and `docs/demo/`) finds no other publication restriction. What remains describes what a command prints, which is not policy.
- `make check` passed.

## Review — banner-wording-2, round 2 — bsc-reviewer

- Reviewed `/tmp/bsc-review/banner-wording-2-r2/staged.diff` and the revised
  closing notebook paragraph. Reused this loop's round-1 code, rendering,
  credit, caller and policy-consistency review.
- Verified lock ownership (`bsc-implementer banner-wording`), `HERDR_ENV=1`,
  and requesting Claude identity, repository and pane `wF:p1` through Herdr.
- BW-002: fixed. The closing paragraph distinguishes record tables kept out
  of version control from the ranking, movement map and PDFs that may be
  shared or published with TIMS and CCRS credits.
- Independent check: evaluated the exact closing Markdown AST expression
  with made-up config/path values. Confirmed credited-publication wording,
  table/version-control distinction and absence of the old own-computer
  instruction. Notebook and other changed Python files parse.
- Searched current README, AGENTS, docs, notebook, source and tests for the
  obsolete publication/privacy phrases, removed `prepared_for`/`--for`
  references and old README anchor; no matches (rg exit 1). Historical
  review records were outside this live-text search.
- Evidence reused: implementer's reported round-2 `make check` success.
  No full suite, browser/print run, protected-data access or independent
  source-terms/legal verification; round 1's limits continue to apply.
- Findings: no new correctness findings.
- Verdict: **accepted, banner-wording-2 round 2**. BW-002 is fixed in the
  staged snapshot. This completes the review loop; acceptance authorizes no
  commit, push or merge.

## Finding ledger — banner-wording-2, round 2

| ID | Severity | Blocking | Status | Evidence |
| --- | --- | --- | --- | --- |
| BW-002 | P2 | Resolved | fixed | Exact closing notebook text permits credited publication of ranking/maps/PDFs and separately excludes record tables from version control. |
