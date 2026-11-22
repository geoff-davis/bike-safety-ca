# Review: attainable

## Current state

- Status: complete (accepted in round 2)
- Next action: none
- Base commit: `a9bc50e`; snapshot: `/tmp/bsc-review/attainable-r1/`
- Open findings: none
- Decisions needed from the user: none

## Loop

- Loop ID and round: `attainable-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-attainable`
- Reviewer: `bsc-reviewer` (Codex)
- Authorized scope: review requests and replies only
- Expires (UTC): 2026-11-22 20:20

## Handoff, round 1

- Tier: Medium
- Purpose: issue #2, part 1. The attainable-score simulation was a scratch script (its copy is in issue #2). It becomes `src/bike_safety_ca/checks/attainable.py`, with tests in `tests/test_attainable.py`.
- What the check does, per hold-out window, all cyclists:
  - fits `rank_intersections`;
  - draws each intersection's rate from its gamma posterior (shape = prior_shape + observed, rate = prior_shape/predicted + 1), scaled so the expected later total equals the recorded one;
  - draws Poisson later counts, 2,000 replicates (seed 20261117), in chunks of 100 to bound memory;
  - scores the model's `eb` ranking on each replicate;
  - reports the real score, the simulated mean and 5%/95%, the share of draws below the real score, the oracle mean (each draw ranked by its own rates, every 10th draw), the no-spread mean and the car-only score.

  Windows using the blend get no simulated figures. `rank_scores` is a vectorised `rank_score`.
- Differences from the scratch script: chunked draws, NaN for draws with no hits, a CLI like the hold-out's, and the rank score checked against `rank_score` in a test.
- Docs:
  - the companion note's stale nine-city table is replaced by the rerun, with its reading updated;
  - the write-up's section 6.4 and section 10 are updated;
  - the guide gets a paragraph on the command.
- Rerun: the real rank scores reproduce the current city table exactly (for example, Berkeley's mean is 0.795). The nine cities took about 2 minutes in all.
- Checks: `make check` passed (600 tests, coverage 93.9%); markdownlint is clean.
- Please check: the posterior and scaling maths, the vectorised rank score with ties, the oracle sampling (the `range(-start % ORACLE_STEP, ...)` index), the RNG stream (whether results depend on CHUNK), and whether the doc readings follow from the table.

## Review, round 1 — bsc-reviewer

- Loop: `attainable-1`, round 1.
- Reviewed `/tmp/bsc-review/attainable-r1/staged.diff`, the new module and
  tests, relevant hold-out/model/synthetic source, and changed documentation.
- Verified lock ownership (`bsc-implementer attainable`), `HERDR_ENV=1`,
  and requesting Claude identity, repository and pane `wF:p1` through Herdr.
- Maths: posterior shape/rate and expected-total scaling agree with the
  existing gamma blend and forecast. The fixed-score vectorized AUC uses
  the same midrank formula as `rank_score`; no tie-weight discrepancy found.
  Oracle indexing selects global draw indices 0, 10, 20, etc.; independently
  checked six chunk sizes and eight draw counts, including partial chunks.
- RNG answer: results DO depend on `CHUNK`. Gamma, predictive Poisson and
  no-spread Poisson draws share one generator and are interleaved per chunk;
  changing chunk boundaries changes which random values feed each component.
  Seed repetition with the same CHUNK is reproducible. This is a reproducibility
  caveat, not a blocking finding: no chunk-independent stream is promised.
  Independent component generators would be an option if that is desired.
- Documentation: table arithmetic supports Berkeley's 0.019 average
  shortfall and 0.083 expected-score gap from Huntington Beach. The described
  posterior simulation, fallback omission and calibration to the recorded
  total agree with the implementation. No protected data opened or table
  entries verified against records.
- Evidence reused: implementer's reported 600-test `make check`, 93.9%
  coverage, markdownlint and nine-city rerun results. Did not independently
  rerun those checks or install dependencies.
- Probe: extracted the exact percentile RHS from the snapshot AST and
  evaluated it using minimal vector-comparison/mean stand-ins with Python
  IEEE NaNs. This isolates the expression's comparison and denominator
  behavior; it is not a full NumPy or fitted-city integration test.
- Verdict: **changes required, round 1**, for AT-001. No other correctness
  findings. Acceptance of a later revision authorizes no commit, push or merge.

### AT-001 — P2, blocking, confirmed: undefined AUCs become low percentiles

- Location: snapshot `src/bike_safety_ca/checks/attainable.py:150`.
- `rank_scores` intentionally returns NaN for no-hit/all-hit replicates;
  simulation means and quantiles correctly skip those NaNs. But
  `np.mean(sims < real)` includes them in the denominator because comparing
  NaN with a number is false. For simulated scores `[NaN, 0.6, 0.8]` and
  real score 0.7, the exact expression returns 1/3 instead of the 1/2 share
  among defined simulated scores. The probe confirmed these outputs.
- This is reachable for a successfully fitted city with few later crashes:
  the code simulates whenever the later total is positive, even if it is
  only one, and Poisson predictive draws can have no crashes. The bias can
  then be large, making the real score look unusually low.
- There is a second manifestation in the same expression: when every
  intersection has a real later crash, `rank_score` returns NaN even though
  `later.sum() > 0`. Comparing simulated scores against that NaN returns
  false for every draw, so the report says 0% instead of missing. Probe
  `[0.6, 0.8]` against real NaN confirmed 0.0. With no finite simulated
  scores, the percentile is likewise undefined, not zero.
- Required correction: compute the share over finite simulated scores only,
  and return NaN when the real score is non-finite or no finite simulated
  scores remain. Add focused tests for mixed valid/NaN simulated scores,
  undefined real AUC and an all-invalid simulation result.
- Status: open. This blocks the stated purpose of reporting how unusual
  the real score is under the simulation.

## Finding ledger, round 1

| ID | Severity | Blocking | Location | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| AT-001 | P2 | Yes | `src/bike_safety_ca/checks/attainable.py:150` | open | Exact extracted percentile expression gives 1/3 instead of 1/2 with a NaN replicate, and 0.0 against an undefined real AUC. |

## Handoff, round 2

- Snapshot: `/tmp/bsc-review/attainable-r2/`. Loop `attainable-1`, round 2 of 3. Expires (UTC): 2026-11-22 20:25.
- AT-001 fixed: new `share_below(sims, real)` drops draws without a score and returns NaN when the real score is NaN or no draw has a score. Two focused tests are added (`test_draws_with_no_score_are_left_out_of_the_share_below`, `test_the_share_below_is_empty_without_a_real_score_or_any_scored_draw`).
- CHUNK caveat: a comment now says the draws depend on CHUNK as well as the seed, so it should stay fixed.
- `make check` passed.

## Review, round 2 — bsc-reviewer

- Loop: `attainable-1`, round 2.
- Snapshot reviewed: `/tmp/bsc-review/attainable-r2/staged.diff`, new
  `share_below`, its caller and regression tests, CHUNK comment, and staged
  documentation. Reused round 1's wider mathematical and implementation
  review; no additional correctness findings.
- Verified lock ownership (`bsc-implementer attainable`), `HERDR_ENV=1`,
  and the requesting Claude's repository and pane `wF:p1` through Herdr.
- AT-001: fixed. `share_below` filters with `np.isfinite`, divides only by
  the remaining draws, and returns NaN for a non-finite real score or an
  empty valid set. `attainable` now calls this helper for the reported share.
- Independent probe: extracted and executed the exact snapshot helper with
  minimal NumPy indexing/comparison/mean stand-ins. Seven checks passed:
  mixed NaN/finite draws gives 0.5 for the original example; undefined real
  AUC, all-invalid draws and an empty input give NaN; infinite draws are
  excluded; infinite real AUC gives NaN; ties retain strict-below semantics.
  This is an isolated logic probe, not a NumPy integration test.
- Inspected the two added regression tests: they cover mixed valid/NaN
  scores, undefined real AUC and an all-NaN simulated result. Changed source
  and tests parse with Python AST. The RNG comment now correctly records
  the dependency on CHUNK without changing the simulation stream.
- Evidence reused: implementer's reported round-2 `make check` success and
  round-1 rerun/coverage evidence. No full suite, protected-data access or
  independent aggregate rerun performed; round 1's limits still apply.
- Verdict: **accepted, round 2**. AT-001 is fixed in the staged snapshot.
  This completes the review loop; acceptance authorizes no commit, push or
  merge.

## Finding ledger, round 2

| ID | Severity | Blocking | Status | Evidence |
| --- | --- | --- | --- | --- |
| AT-001 | P2 | Resolved | fixed | Finite-only helper used by the reporting caller; requested regression cases added; seven isolated helper checks passed. |
