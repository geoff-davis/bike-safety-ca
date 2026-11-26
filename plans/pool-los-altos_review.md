# Review: Los Altos fitted with its neighbours, the study area retired

## Handoff, round 1

- Implementer: `bsc-implementer`, pane `wF:p1`. Base commit `4881f53` (branch `pool-los-altos`, on top of `evaluation`). Snapshot: `/tmp/bsc-review/pool-los-altos-r1/` (`staged.diff`, `tree/`). Round 1 of at most 3. Expires (UTC): `2026-11-26T20:55:08Z`.
- Decided by the owner: the Los Altos study area (circles around schools plus the city limit) is retired in favour of fitting Los Altos with five whole neighbouring cities. The code that draws an area from schools stays; no config uses it. Tables a command produces are rerun; one-off study-area figures stay, labelled.
- Files under review (the documents are exempt): `config/los_altos.yaml`, `config/pool_santa_clara.yaml` (removed), `src/bike_safety_ca/checks/candidates.py`, `tests/study_area_config.yaml`, `tests/test_area.py`, `tests/test_synthetic_holdout.py`, `notebooks/walkthrough.py`, `case_studies/los_altos/expected_holdout.csv`.
- What changed:
  - `config/los_altos.yaml` is now the former `config/pool_santa_clara.yaml` (six cities, first year 2015, Census limits, no pinned map date) with a new header and the map framings (`prints`) of the old config. `pool_santa_clara.yaml` is removed: it was the same area.
  - The old config's settings are kept as `tests/study_area_config.yaml`, without the framings, for `tests/test_area.py`, which tests the school-circle settings.
  - `candidates` leaves out `los_altos` by default as well as `pool_*`: it is a pooled area that overlaps Cupertino, Mountain View, Palo Alto and Sunnyvale, which are scored as cities. The cross-city check is told with `--pool 'pool_*' los_altos` (documents).
  - Expected value changed in `test_los_altos_config_loads`: the config no longer takes in unincorporated county, so it has no `municipality_aliases`; the test now asserts the six cities and that no school-circle setting is present.
  - `case_studies/los_altos/expected_holdout.csv` is the hold-out table of the six-city fit (aggregate scores and counts; the hold-out command's `--expect` matches it).
  - The notebook's two text passages point at `config/los_altos_city.yaml` as the config to copy.
- What to report: a config, test or command left pointing at the removed file or at settings the new config lacks; whether leaving `los_altos` out of `candidates` by default can drop a city that should be scored; whether the `prints` framings can break a command on the new config.
- Verification: `make check` passes (711 tests; one fewer because `tests/test_config.py` runs once per config file). The hold-out command was run on the six-city tables and matches the saved table.
- Known limitations: the `prints` corner names were written for the old street download and have not been checked against the new one; the map and its PDFs have not been regenerated. The test count of the cross-city check on the new name was not rerun.

## Review — pool-los-altos, round 1

Verdict: **accepted, round 1**, for the implementation/configuration scope. No blocking correctness findings in the files named for review. One nonblocking documentation correction is recorded below; the handoff explicitly exempts documents.

The new `los_altos.yaml` is semantically identical to the deleted six-city pool config apart from its retained `prints`. It removes the unincorporated area, school-circle settings, custom city-limit URL and pinned map date as intended. The former study-area settings are isolated in the test fixture, and the affected area/config assertions point to the appropriate config. No live source/test/notebook reference to the deleted pool filename was found. The candidate parser's exact-name exclusion of `los_altos` leaves `los_altos_city` available; it does not drop the city-only comparison.

### PL-001 — nonblocking: one reproduction command still omits the renamed pool

Location: `docs/forecasting_model.md:1317`, the “Rerun with repository commands” table.

That row still says `checks.cities --configs config --pool 'pool_*' --out <folder>`. The pool is now named `los_altos`, so that pattern no longer classifies it as pooled. The cross-city command will include its whole six-city area among the individual-city rows and child/severity summaries, alongside its member cities, and omit it from the pooled comparisons. Add `los_altos` after `'pool_*'`, as already done in the guide, the other model-write-up command and `where_the_ranking_helps.md`. This is a concrete stale appendix command; it does not require changing the reviewed implementation or pool-selection design.

### Verification and material limits

- Parsed the new config and the deleted pool config from the staged diff: all non-`prints` settings match. Confirmed the duplicate config is absent and the test fixture retains 18 schools and the original buffer.
- Executed the actual candidate argument-parser path with a stopped-before-loading stub: default exclusions match `los_altos` and preserve `los_altos_city`. Checked the cross-city classifier against both the stale and corrected pattern lists.
- Checked all 66 rows of the supplied aggregate hold-out CSV for rank-score bounds, monotone top-25/50/100 counts bounded by later totals, and unscored rows below the existing 30-event threshold. This checks internal consistency, not reproduction of scores from records.
- Inspected the printing path. A named framing must resolve to exactly one map intersection; otherwise `framing_url` raises and PDF printing stops. The old corner names cannot be validated against the new map within this snapshot-only review. This is the handoff's acknowledged unresolved verification limit, not a confirmed missing-corner finding. Acceptance does not establish that the new map/PDF command completes with those framings.

Full pytest/`make check`, cross-city numerical output and regenerated maps/PDFs were not independently run because numerical/dataframe/test dependencies and permissible map inputs are unavailable here. The handoff reports 711 passing tests and a matching six-city hold-out run. No protected paths, real crash records or map data were opened; the reviewed hold-out file contains the authorized aggregate results only.

Ledger: no blocking findings; PL-001 open as a nonblocking exempt-document correction. Pool-los-altos ends accepted at round 1. Implementer releases the reviewer lock. Review does not authorize a commit, push, merge or publication.
