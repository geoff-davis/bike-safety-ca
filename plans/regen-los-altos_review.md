# Review: case study rerun on the six cities, one config comment

## Handoff, round 1

- Implementer: `bsc-implementer`, pane `wF:p1`. Base commit `9e2b5bc` (branch `regen-los-altos`, from `origin/main`). Snapshot: `/tmp/bsc-review/regen-los-altos-r1/` (`staged.diff`, `tree/`). Round 1 of at most 3. Expires (UTC): `2026-11-27T00:27:29Z`.
- File under review: `config/los_altos.yaml`. One comment line: it said the agency reassignment was "as in config/los_altos.yaml", which is the file itself since the study area was retired; it now names `config/los_altos_city.yaml`, which holds the same setting. No setting changes.
- Exempt, for context only: `docs/case_study_los_altos.md`, whose sensitivity and police-reporting sections now report runs of the repository's own commands on the six-city tables (aggregate scores and counts).
- What to report: whether the comment is now accurate against `config/los_altos_city.yaml`.
- Verification: `make check` passes (723 tests); the document hooks pass.

## Review — regen-los-altos, round 1

Verdict: **accepted, round 1**. No findings.

The comment now points to an existing config whose `agency_reassignments` setting exactly matches this file. Parsed both snapshot YAML files and verified equality; the config diff changes only a comment and leaves every setting unchanged. No runtime tests were needed for this comment-only change. The handoff reports `make check` passing (723 tests); that suite was not independently rerun. The exempt case-study document and its reported numerical reruns are context, not independently validated results in this review. No protected paths or records were opened.

Ledger: no findings; regen-los-altos ends accepted at round 1. Implementer releases the reviewer lock. Review does not authorize a commit, push, merge or publication.

## Handoff, second loop, round 1

- Implementer: `bsc-implementer`. Snapshot: `/tmp/bsc-review/regen-los-altos-b-r1/`. Round 1 of at most 3. Expires (UTC): `2026-11-27T07:02:52Z`. Base: `c726835` (the branch with `origin/main` at 88d0e04 merged in).
- What changed: after the edge-placement fix (#36) the six-city hold-out and sensitivity checks were run again. `case_studies/los_altos/expected_holdout.csv` is the hold-out command's new output (aggregates by window and ranking, no records), and `docs/case_study_los_altos.md` quotes the new figures. No code changes.
- Why the expected values change: the fix adds 60 crashes (15 bike) recorded just outside the area outline to the 6,367 placed; scores move by 0.002 at most on the six cities.
- Checks: `make check` passes (729). The reporting section is not rerun: that check counts reports by agency and places no crash.
- To review: that the figures in the document agree with the CSV, and that nothing in the CSV is a record.

## Review — regen-los-altos-b, round 1

Verdict: **accepted, round 1**. No blocking findings.

The changed CSV contains 66 aggregate rows keyed by training/test window, outcome, area and ranking, with method labels, total crash counts and ranking statistics. It contains no individual crash IDs, record attributes, coordinates or individual records. No protected paths or records were opened.

Parsed the CSV and checked its exact 12-column schema, unique aggregate keys, numeric bounds, monotone top-25/50/100 counts, consistent training totals across rankings/areas, and suppression of all score columns where later crashes are fewer than 30. All passed. Independently calculated the document's CSV-derived values: six-city street-length means 0.844/0.825, Los Altos mean 0.849 over two windows, Los Altos past-count mean 0.680, and all-cyclist ranking tested on children mean 0.818. Window counts (458/189/340 and 144/57/106), per-window street-length scores, child training range 227–371, total placed cyclists 1,494, and summed later-window observations 987 agree. The overlapping hold-out windows are treated as separate observations, not unique crashes.

The displayed sensitivity table supports its stated maximum 0.002 departure from the configured baseline, and its configured row agrees with the CSV-derived scores and total cyclist count. Arithmetic of the stated additions is consistent (6,367 + 60 = 6,427; 1,479 + 15 = 1,494). The CSV does not contain the sensitivity variants, severity-filtered runs, city-only fit or city-by-city scores; those numerical reruns and the provenance of the new expected outputs cannot be independently verified from this snapshot. No model was fitted or scored in this review, and the implementer's reported 729 passing tests were not independently rerun.

Ledger: no blocking findings; regen-los-altos-b accepted at round 1. Implementer releases the reviewer lock. Acceptance does not authorize commit, push, merge or publication.
