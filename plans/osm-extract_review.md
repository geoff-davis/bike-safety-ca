# Review: osm-extract

## Current state

- Status: complete (accepted in round 2)
- Next action: none
- Base commit: `9f97f98`; snapshot: `/tmp/bsc-review/osm-extract-r1/`
- Open findings: none
- Decisions needed from the user: none

## Loop

- Loop ID and round: `osm-extract-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-osm-extract`
- Reviewer: `bsc-reviewer` (Codex)
- Authorized scope: review requests and replies only
- Expires (UTC): 2026-11-22 22:25

## Handoff, round 1

- Tier: Medium
- Purpose: issue #2, part 3. The scratch `extract.py` (its copy is in issue #2) becomes `src/bike_safety_ca/download/osm_extract.py` plus a `--extract PATH.osm.pbf` option on `python -m bike_safety_ca.network`. The download step then cuts the streets in the padded box from a regional extract instead of asking Overpass, and writes the same three files in the same shape, so the build step and the reuse check work unchanged.
- osmium is an optional extra (`extract`) and is also in the dev group, so CI runs its tests.
- Refactor: `osm.download` is split into `osm.reuse` (the saved-file check, unchanged logic) and `osm.save` (the writes; now takes an optional `source` for the note). The cutter uses both, and the existing download tests pass unchanged.
- Differences from the scratch script:
  - one box per call;
  - the header-box check raises before anything is written;
  - `osm.check` refuses an empty cut;
  - `--extract` together with a config `osm_date` is a usage error;
  - an `isinstance(item, osmium.osm.Way)` check, for mypy.
- Real-data check (totals only, run outside the snapshot): Santa Monica's saved Overpass box (download of 2026-11-17), cut from Geofabrik's socal extract (base 2026-11-20). All 26,309 saved ways are in the cut, plus 1 extra; node counts are equal (91,541). It took 23 s and 2.4 GB peak memory.
- Tests: `tests/test_osm_extract.py` (6, on a made-up OSM XML extract) and one CLI test in `tests/test_commands.py`. `make check` passed (609 tests, coverage 93.96%).
- Docs: the guide's "The area and its streets" gets a paragraph on `--extract`; the companion note's "When the street download fails" points to it.
- Please check:
  - way selection (the bbox pre-filter, then the intersects test), including ways that cross the box with no node inside;
  - that `with_locations()` before `with_filter(KeyFilter("highway"))` still locates untagged nodes (the tests rely on this);
  - the reuse and refuse semantics after the refactor;
  - the header-box containment test.

## Review, round 1 — bsc-reviewer

- Loop: `osm-extract-1`, round 1.
- Reviewed `/tmp/bsc-review/osm-extract-r1/staged.diff`, the cutter, OSM
  reuse/save refactor, CLI, synthetic tests, changed docs, dependency
  declarations and lock metadata, downstream street builder and existing
  cache tests. No protected data paths opened.
- Verified lock ownership (`bsc-implementer osm-extract`), `HERDR_ENV=1`,
  and the requesting Claude's repository and pane `wF:p1` through Herdr.
- Selection review: the coordinate bbox prefilter does not reject a segment
  crossing the query box with both endpoints outside it; the line intersection
  check rejects bbox-only false positives. Accepted ways retain all node
  references and coordinates needed by the existing builder. The new XML
  test explicitly includes untagged nodes, a crossing-only way, a missed
  corner, missing nodes and non-highway ways.
- Header/reuse review: known header extents are checked against the padded
  box before writes; missing bounds warn. The refactored cache comparison
  retains the old area/date and legacy-no-metadata behavior. Overwrite
  bypasses reuse; empty cuts are checked before saving. Inspection found no
  unintended change in download/save behavior.
- Independent checks: project and lock TOML parse, optional/dev osmium
  declarations and root optional lock entry agree, and changed Python files
  parse. Extracted the exact CLI `main` AST and invoked its documented
  arguments with the snapshot config parsed by YAML and configuration/step
  loading stand-ins: it exits 2 at the pinned-date guard before any download
  or build call, confirming OE-001.
- Evidence reused: implementer's 609-test `make check`, coverage and XML/
  CLI test results, and aggregate regional-extract comparison. Did not rerun
  the suite, install dependencies, read real extracts, or independently
  verify Overpass selection equivalence. In particular, actual pyosmium
  location/filter ordering is supported here by the reported XML-test run,
  not an independently executed integration probe.
- Verdict: **changes required, round 1**, for OE-001. No other correctness
  findings. A review verdict authorizes no commit, push or merge.

### OE-001 — P2, blocking, confirmed: new guide command always rejects its config

- Location: snapshot `docs/guide.md:93–96`.
- The new example passes `--extract path/to/norcal-latest.osm.pbf` with
  `config/los_altos.yaml`. That checked-in config sets
  `osm_date: "2026-08-22T23:47:01Z"` (line 74). The newly added CLI guard
  (`network/__main__.py:45–46`) rejects exactly this combination.
- Concrete failing case: run the guide's command after installing the
  extract extra, with any valid regional extract. It exits with argparse
  status 2 and “--extract holds the map of its own date; drop osm_date or
  --extract”, before attempting the extraction. The exact-main probe
  reproduced that branch without touching data or calling external services.
- Impact: the documented entry point for the new fallback cannot run as
  shown. The later sentence explaining that `osm_date` is incompatible
  does not supply the required config preparation for this example.
- Required correction: use a checked-in unpinned config in the example, or
  explicitly show preparing a separate config without `osm_date` before the
  command. Keep the date guard; it correctly protects pinned analyses.
- Status: open.

## Finding ledger, round 1

| ID | Severity | Blocking | Location | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| OE-001 | P2 | Yes | `docs/guide.md:95` | open | Example selects pinned Los Altos config; exact CLI main probe exits 2 at the extract/date guard. |

## Handoff, round 2

- Snapshot: `/tmp/bsc-review/osm-extract-r2/`. Loop `osm-extract-1`, round 2 of 3. Expires (UTC): 2026-11-22 22:27.
- OE-001 fixed: the guide's example now uses `config/san_diego.yaml` (no `osm_date`; the case that needed an extract) with `socal-latest.osm.pbf`. The text says a config pinning `osm_date`, such as `config/los_altos.yaml`, refuses `--extract`. The guard is kept.
- Docs only since round 1; markdownlint is clean.

## Review, round 2 — bsc-reviewer

- Loop: `osm-extract-1`, round 2.
- Reviewed `/tmp/bsc-review/osm-extract-r2/staged.diff`, the revised guide
  example, `config/san_diego.yaml`, the pinned Los Altos config and the CLI
  date guard/dispatch. Reused round 1's broader implementation review.
- Verified lock ownership (`bsc-implementer osm-extract`), `HERDR_ENV=1`,
  and the requesting Claude's repository and pane `wF:p1` through Herdr.
- OE-001: fixed. The example now uses `config/san_diego.yaml` and
  `socal-latest.osm.pbf`; the snapshot San Diego config has neither an
  `osm_date` nor a `streets_file` that would bypass the extraction. The
  adjacent prose explicitly explains why the pinned Los Altos config
  refuses this option, and the protective CLI guard is unchanged.
- Independent check: parsed both configs with YAML and executed the exact
  snapshot `main` via AST extraction, isolating its `download` step with
  config/outline/geometry/cut stand-ins. The revised guide's config and
  extract options pass the date guard and dispatch once to the cutter with
  the supplied extract path. No downloads, files or protected data were
  accessed by that probe.
- Evidence reused: round 1's reported suite/coverage/integration checks and
  the implementer's round-2 markdownlint result. No full suite, live
  regional-extract run or external equivalence check repeated. Round 1's
  integration and data-verification limits continue to apply.
- Findings: no new correctness findings.
- Verdict: **accepted, round 2**. OE-001 is fixed in the staged snapshot.
  This completes the review loop; acceptance authorizes no commit, push or
  merge.

## Finding ledger, round 2

| ID | Severity | Blocking | Status | Evidence |
| --- | --- | --- | --- | --- |
| OE-001 | P2 | Resolved | fixed | Guide uses unpinned San Diego config; isolated exact-main probe passes the guard and reaches the cutter with the documented extract option. |
