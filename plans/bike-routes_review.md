# Review: bike-routes

## Current state

- Status: complete (accepted in round 2)
- Next action: none
- Base commit: `b6c2afe`; snapshot: `/tmp/bsc-review/bike-routes-r1/`
- Open findings: none
- Decisions needed from the user: none

## Loop

- Loop ID and round: `bike-routes-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-bike-routes`
- Reviewer: `bsc-reviewer` (Codex)
- Authorized scope: review requests and replies only
- Expires (UTC): 2026-11-22 22:53

## Handoff, round 1

- Tier: Medium
- Purpose: issue #2, part 2. The scratch `bikeroute.py` and `fetch_routes.py` (copies in issue #2) become `src/bike_safety_ca/checks/bike_routes.py`.
- What it does: marks each intersection "lane" / "route, no lane" / "neither" from today's OSM tags and the route relations, within 20 m. Per window it refits the street-length model with the two flags and reports, beside the plain model: rank score, top-100 share, the multipliers, a likelihood-ratio p-value (df = flags kept) and later/expected by group.
- Model change: `fit_street_model` gains an optional `extra` DataFrame of design columns, used as given (not logged), and returns `log_likelihood`. With `extra=None` nothing changes. This replaces the scratch script's use of the private `_fit_spread`, and with it the caveat that its refit differed slightly from the model in 4 of 21 windows.
- `osm.check` and `osm.run` gain `require_elements` (default True), because a city may rightly have no route relations.
- Relations: one Overpass query per city, saved as `overpass_bike_routes.json` beside the street download, with that download's box. A saved file for another box is refused unless `--overwrite` is given; `--routes FILE` gives a file instead.
- Windows the model leaves to the blend are not refitted; a flag no site has, or every site has, is dropped before the fit.
- Real run (totals only; data outside the snapshot), seven cities and 20 fitted windows:
  - lane multipliers 1.3 to 2.6;
  - p < 0.01 in 17 windows;
  - the rank score rose by 0.002 to 0.012 in 16 windows and fell by up to 0.005 in 4.

  The companion note's "Where cycling is separated" paragraph reports this.
- Tests: `tests/test_bike_routes.py` (8, made-up data). Rebased on main after #15 merged; `make check` passed (617 tests).
- Please check:
  - the `extra` path in `fit_street_model` (index alignment, AIC count);
  - the LR test when a flag is dropped;
  - `flags()` precedence (lane over route);
  - the saved-relations box check;
  - whether the doc's figures follow from the description above.

## Review, round 1 — bsc-reviewer

- Loop: `bike-routes-1`, round 1.
- Reviewed `/tmp/bsc-review/bike-routes-r1/staged.diff`, new check and tests,
  model design construction/AIC, OSM answer validation and related method
  documentation. No protected data paths opened.
- Verified lock ownership (`bsc-implementer bike-routes`), `HERDR_ENV=1`,
  and requesting Claude identity, repository and pane `wF:p1` through Herdr.
- Model path: extra columns are aligned to the bike index and appended after
  the existing terms; `extra=None` leaves the fitting design unchanged.
  AIC adds one parameter per supplied extra column, which is appropriate
  only for identifiable independent columns (BR-001). The added
  log-likelihood return does not alter the ordinary prediction path.
- Flags/cache: lane takes precedence over route in `np.select`. Constant
  columns are dropped, but this is insufficient when neither is absent.
  The standard plain-JSON street-download metadata path and saved route-box
  comparison agree; overwrite bypasses the cached answer. Empty relation
  answers are allowed while the default street request still requires
  elements and all requests still reject error remarks.
- Independent probe: executed the exact constant-column filtering expression
  extracted from the snapshot AST with minimal DataFrame/std/indexing
  stand-ins. For complementary lane/route columns, both survive. A standard
  scalar Gaussian-elimination probe gave base design rank 3 and augmented
  rank 4 despite two extra columns. At LR=4, chi-square tails are 0.1353
  for the reported df=2 and 0.04550 for the effective df=1.
- Documentation arithmetic: seven cities times three windows minus one
  fallback gives 20 fitted windows; 16 improvements plus four decreases
  is consistent with that count. Aggregate multipliers and p-value counts
  were not checked against records. As already explained in the method
  note's assumption 11, the shared-street likelihood treats dependent
  corners as independent; these chi-square p-values remain nominal
  diagnostics, not independently validated significance measurements.
- Evidence reused: implementer's reported 617-test `make check`, eight new
  synthetic tests and aggregate real-run summary. Did not rerun the suite,
  fit a numerical model or issue a live Overpass request. Changed Python
  files parse. The matrix probe establishes the rank defect without
  depending on optimizer behavior or protected data.
- Verdict: **changes required, round 1**, for BR-001. No other blocking
  correctness findings. A review verdict authorizes no commit, push or merge.

### BR-001 — P2, blocking, confirmed: absent reference group leaves redundant flags

- Location: snapshot `src/bike_safety_ca/checks/bike_routes.py:143–147`
  and the degrees-of-freedom calculation at line 173.
- Concrete case: a valid group series alternates `lane` and `route, no lane`
  and contains no `neither`. Both dummy columns vary, so the std filter
  keeps both, but `lane + route = 1` at every intersection. The model also
  includes an intercept, making one of the added columns redundant.
- Confirmed with six made-up sites and baseline columns `[1, i, i*i]`:
  the base rank is 3 and the augmented rank is 4, while the code counts
  two extra degrees of freedom. Adding 1 to the intercept and subtracting
  1 from both flag coefficients leaves every prediction unchanged, so the
  displayed flag multipliers are not identifiable either.
- Impact: for a likelihood-ratio statistic of 4 the code reports p=0.1353
  instead of the one-added-dimension tail 0.04550. The AIC likewise counts
  an extra redundant parameter. The comparison can therefore misstate both
  the model complexity and evidence for flags in a supported group layout.
- Required correction: encode the observed groups with a valid reference
  category (drop a redundant dummy when neither is absent), and make the
  multiplier reference explicit. Use the effective number of independent
  added terms for AIC/LR counting, or reject unsupported rank-deficient
  designs. Add a synthetic case with lane/route groups but no neither;
  retain coverage for an absent route group and for all three groups.
- Status: open.

## Finding ledger, round 1

| ID | Severity | Blocking | Location | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| BR-001 | P2 | Yes | `checks/bike_routes.py:147` | open | Complementary varying indicators both survive the exact filter but add only one design dimension; coefficients are non-identifiable and df/AIC overcount. |

## Handoff, round 2

- Snapshot: `/tmp/bsc-review/bike-routes-r2/`. Loop `bike-routes-1`, round 2 of 3. Expires (UTC): 2026-11-22 22:57.
- BR-001 fixed: `compare` builds one 0/1 column per group present, less a reference group: "neither" when any site has it, else the last group present in GROUPS order. The columns can no longer add up to the intercept, and the LR df equals the identifiable columns. The table gains a "reference group" column, and the module docstring says the multipliers are relative to it.
- New tests:
  - `test_without_a_neither_group_one_flag_is_fitted_against_the_other`: lane and route only; one column, reference "route, no lane";
  - `test_the_reference_is_neither_when_any_corner_has_it`.
- The real-city figures in the doc are unchanged: all seven cities have "neither" sites (shares 47% to 72%), so the encoding there is the same as in round 1.
- `make check` passed.

## Review, round 2 — bsc-reviewer

- Loop: `bike-routes-1`, round 2.
- Reviewed `/tmp/bsc-review/bike-routes-r2/staged.diff`, revised encoding,
  reference labeling, LR/AIC consumers and added tests. Reused round 1's
  broader model, route-cache, flag and documentation review.
- Verified lock ownership (`bsc-implementer bike-routes`), `HERDR_ENV=1`,
  and requesting Claude identity, repository and pane `wF:p1` through Herdr.
- BR-001: fixed. The fit now includes one indicator for each observed group
  except an observed reference. GROUPS order makes neither the reference
  whenever present; lane/route-only data use route as reference. The table
  names that reference, and the module notes explain the multiplier basis.
  The reference indicator is not passed into the model, so the original
  redundant-dummy overcount is removed from both AIC and LR df.
- Independent check: executed the exact `present`/`reference`/`extra`
  statements extracted from the snapshot AST with minimal Series/DataFrame
  stand-ins. Across all seven non-empty subsets of the three categories,
  k observed groups yielded k-1 flag columns and an intercept-plus-dummy
  matrix of rank k (verified by scalar Gaussian elimination). This includes
  the original lane/route-only failing case, every single-group case and
  all three groups. Changed source/test files parse.
- Inspected new synthetic tests for the absent-neither layout and the
  ordinary three-group layout; the existing absent-route test is retained.
  The real-city figures remain compatible with unchanged three-group
  encoding, per the implementer's report that all seven have neither sites.
- Evidence reused: implementer's reported round-2 `make check` success and
  round-1 suite and aggregate-run evidence.
- Limits: did not independently refit models, rerun the suite, fetch routes
  or access protected records. The encoding probe tests category rank,
  not every possible accidental dependence on other model predictors.
  Round 1's statistical and aggregate-verification limits still apply.
- Findings: no new correctness findings.
- Verdict: **accepted, round 2**. BR-001 is fixed in the staged snapshot.
  This completes the review loop; acceptance authorizes no commit, push or
  merge.

## Finding ledger, round 2

| ID | Severity | Blocking | Status | Evidence |
| --- | --- | --- | --- | --- |
| BR-001 | P2 | Resolved | fixed | Observed reference omitted and labeled; all seven category subsets pass independent encoding/rank probes; missing-neither and three-group regression tests added. |
