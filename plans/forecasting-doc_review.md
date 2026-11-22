# Review: forecasting-doc

## Current state

- Status: complete (accepted in round 2)
- Next action: none
- Base commit: `c87bd4e`; snapshot: `/tmp/bsc-review/forecasting-doc-r1/`
- Open findings: none
- Decisions needed from the user: none

## Loop

- Loop ID and round: `forecasting-doc-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), worktree `/home/geoff/Projects/personal/bike-safety-ca/.claude/worktrees/agent-a60089f011435b29c`
- Reviewer: `bsc-reviewer` (Codex)
- Authorized scope: review requests and replies only
- Expires (UTC): 2026-11-22 18:50

## Handoff, round 1

- Tier: Large (docs only, so exempt by path, but the user asked for a review because it carries new figures and derivations)
- Change: new `docs/forecasting_model.md`, a full write-up of the forecasting model: assumptions, functional form, why each choice was made, validation and performance tables on California cities, the fallback for cities with less data, the crash-record data (TIMS vs CCRS, the SWITRS to CCRS change, police reporting changes, the reporting check), and an appendix of derivations. `docs/crash_history_method.md` is reduced to a pointer. Links are fixed in README.md, docs/guide.md, docs/county_rates_method.md and docs/where_the_ranking_helps.md, and stale figures are replaced.
- Figures: tables marked fresh were rerun at c87bd4e against the 21 Nov 2026 crash tables; others are labelled "not rerun". You cannot see the data, so do not try to check numbers against it.
- Please check, against the code in the snapshot (`src/bike_safety_ca/`):
  1. The formulas in sections 3 and 7 match what the code computes (crash_history, the street average, the blend, the fallback and pooling).
  2. The derivations in the appendix are mathematically correct (negative binomial marginal, posterior mean, credibility weight, score equations, AUC standard error, top-k with ties).
  3. Internal consistency: the same figure quoted the same way in different places, totals that add up, links and anchors that resolve.
  4. The descriptions of the reporting check and crash placement in section 8 match the code (`checks/`, `reporting/`, `network/locate.py`).
  5. No record-level data: no case IDs, names or single crashes described in identifiable detail.
- Checks run: markdownlint-cli2 0.19.0 on all touched docs, 0 errors. No Python changed.

## Review, round 1 — bsc-reviewer

- Loop: `forecasting-doc-1`, round 1.
- Reviewed the new write-up and changed companion text against the snapshot
  model, ranking, grouping, hold-out/pooling, reporting, merge and placement
  code. The handoff refers to `network/locate.py`; the relevant recovery code
  is actually `crashes/locate.py`, with assignment in `network/junctions.py`.
- Verified the coordination lock names `bsc-implementer forecasting-doc`,
  `HERDR_ENV=1`, and the requesting Claude's repository and pane `wF:p1`.
- Checks: local Markdown targets and heading anchors in all six changed
  documents resolved. Parsed section 6.1: 28 cities, 27 scored, 74 windows,
  17 cities scored for children, 19 always fitted, score range 0.744–0.904
  and median 0.864 agree with the summary. Study-area window totals add to
  593 all-cyclist and 203 child crashes. Numerically checked posterior
  weighting and one-crash multipliers on a grid; the AUC approximation gives
  SE 0.0843 and 0.0487 for 10 and 30 positive intersections, as quoted.
- Inspected the negative-binomial marginal, forecast moments/probabilities,
  Poisson score equations, fallback blend and tie-sharing expression.
  Reporting thresholds, region adjustment, partial-year rules and level-step
  criteria match the inspected source. No record-level identifiers or
  identifiable individual-crash descriptions found in the changed prose.
- Evidence reused: reported markdownlint success and rerun provenance.
- Limits: no protected data opened or aggregate figures checked against
  records. No full suite, actual geometry integration test, or independent
  publisher/reference verification performed. The placement probe below ran
  the exact snapshot function extracted with AST, with synthetic geometry
  stand-ins to exercise its multiple-crossing branch; it wrote no files.
- Verdict: **changes required, round 1**, for FD-001. FD-002 and FD-003
  are confirmed non-blocking corrections, recommended for the same document
  in the next revision. This verdict authorizes no commit, push or merge.

### FD-001 — P2, blocking, confirmed: recovery accepts more than two crossings

- Location: snapshot `docs/forecasting_model.md:1289–1292`.
- The text says two crossings within 60 m are averaged and more crossings
  are ambiguous and left unplaced. `crashes/locate.py:_intersection_location`
  instead averages any number greater than one when the maximum pairwise
  distance is at most `cluster_m` (60 m at the call site).
- Concrete probe: four synthetic crossings at (-10, -10), (-10, 10),
  (10, -10), (10, 10). The exact snapshot function returns point (0, 0),
  status `recovered_divided_road_intersection`, gap 0.0. The documented rule
  predicts rejection. Two divided roads can produce precisely this shape.
- Required correction: describe a cluster of crossings whose maximum
  pairwise separation is at most 60 m; a wider multiple-crossing set is
  ambiguous. This blocks the requested correspondence between section 8's
  placement rules and the code. Status: open.

### FD-002 — P3, non-blocking, confirmed: credibility decomposition needs a singleton case

- Location: snapshot `docs/forecasting_model.md:1523–1525`.
- For a street with one intersection, `n_r=1` and `Y_r=y_i`. The first
  fraction is valid and gives `t(1)`, as section 3.3 and the code do. The
  following expression divides `Y_r-y_i` by `n_r-1`, hence has `0/0` even
  though `Z=0`. For example, `Q=20`, `t(1)=0.3`, `Y_r=y_i=2` gives 0.3 in
  the first expression and division by zero in the second; scalar probe
  confirmed this.
- Recommended correction in appendix A.5: restrict the empirical-mean
  decomposition to `n_r>1` and state that a singleton uses `t(1)` directly.
  Status: open; recommended home: this document's next revision.

### FD-003 — P3, non-blocking, confirmed: fitted quantities total ten, not nine

- Locations: snapshot `docs/forecasting_model.md:245–247` and `:847`.
- The enumerated quantities are five bike-fit parameters
  (`gamma_0`, `b`, `a`, `alpha`, `p`), one car shape, and two pairs of
  street-regression coefficients: `5 + 1 + 2*2 = 10`. The source fits all
  ten when `spread_power` is omitted, as in the production entry point.
- Recommended correction: update both occurrences of nine to ten, or
  explicitly distinguish the bike fit from the auxiliary fits if discussing
  which quantities rely on bike counts. This is not a request to change
  the code's AIC parameter count. Status: open; recommended home: this
  document's next revision.

## Finding ledger, round 1

| ID | Severity | Blocking | Location | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| FD-001 | P2 | Yes | `docs/forecasting_model.md:1289` | open | Exact snapshot recovery function accepts four synthetic crossings within a 60 m cluster. |
| FD-002 | P3 | No | `docs/forecasting_model.md:1523` | open | Singleton scalar probe: first fraction 0.3, decomposition divides by zero. |
| FD-003 | P3 | No | `docs/forecasting_model.md:245` | open | Enumerated and source-fitted quantities count to ten; repeated at line 847. |

## Handoff, round 2

- Snapshot: `/tmp/bsc-review/forecasting-doc-r2/`. Loop `forecasting-doc-1`, round 2 of 3. Expires (UTC): 2026-11-22 18:53.
- FD-001 fixed: section 8.5 step 1 now says several crossings all within 60 m of each other are averaged as one corner, and crossings further apart are ambiguous (confirmed against `crashes/locate.py:_intersection_location`, lines 93–101).
- FD-002 fixed: A.5 says the second form needs $n_r > 1$ and a single-intersection street uses $t(1)$ directly.
- FD-003 fixed: "nine" → "ten" in section 3.5 and section 7.1.
- Also changed since round 1 (implementer's own review):
  - 8.3: a paragraph explaining why the yearly check's "typical year" (Palo Alto 188, Sacramento highway patrol 170) is below the level-step table's before-levels (about 350 and 280): it is a trimmed median over all years, issue #1.
  - 8.2: "four-fifths" → "more than four-fifths (86%)" (4.7 + 41.6 + 40.1 in the 2026 row).
  - 6.2: the sentence about the stale README figure reworded, since the README is now updated.
  - References: Hanley & McNeil checked against Crossref (title, Radiology 143(1) 29–36, 1982, authors match); caveat removed.
- markdownlint: 0 errors.

## Review, round 2 — bsc-reviewer

- Loop: `forecasting-doc-1`, round 2.
- Snapshot: `/tmp/bsc-review/forecasting-doc-r2/`. Reviewed the three fixes
  and the additional edits identified in the round-2 handoff against the
  staged document and relevant snapshot source. Reused round 1's broader
  model, mathematical and table review.
- Checked the coordination lock names `bsc-implementer forecasting-doc`;
  verified `HERDR_ENV=1` and both Herdr identities, including requesting
  Claude `bsc-implementer`, pane `wF:p1`, in the expected repository.
- FD-001: fixed. The revised text accepts several crossings all within
  60 m of each other and rejects wider sets. Reran the exact snapshot
  `_intersection_location` function via AST extraction with synthetic
  geometry stand-ins: four points at coordinates ±10 return
  `recovered_divided_road_intersection`; four at ±50 return
  `ambiguous_multiple_intersections`. Both agree with the revised text.
- FD-002: fixed. A.5 explicitly limits the second form to `n_r > 1` and
  gives `t(1)` for a singleton; the original scalar example returns 0.3
  through the valid first form.
- FD-003: fixed. Both occurrences now say ten, agreeing with the listed
  five bike-fit parameters, car shape and two coefficient pairs.
- Additional checks: 56 local Markdown targets/anchors passed. The newer
  injury-grade shares sum to 86.4%, consistent with the rounded 86%.
  The added distinction between the yearly trimmed median and the
  level-step before-level agrees with `tims.typical_year` and the table's
  approximate totals (222+127=349; 178+102=280). The revised stale-figure
  wording is consistent with the updated README.
- Evidence reused: implementer's reported markdownlint success and
  Crossref verification. The latter was not independently repeated.
- Limits: no protected data accessed, aggregate reruns, full suite or
  real-geometry integration test performed. Round 1's data and reference
  verification limits continue to apply.
- Findings: no new correctness findings; FD-001, FD-002 and FD-003 are
  fixed in the staged snapshot.
- Verdict: **accepted, round 2**. This completes the review loop; acceptance
  authorizes no commit, push or merge.

## Finding ledger, round 2

| ID | Severity | Blocking | Status | Evidence |
| --- | --- | --- | --- | --- |
| FD-001 | P2 | Resolved | fixed | Section 8.5 now describes arbitrary compact crossing clusters; synthetic accepted/rejected cases agree with the exact snapshot function. |
| FD-002 | P3 | No | fixed | A.5 states the domain of the empirical-mean decomposition and the singleton result. |
| FD-003 | P3 | No | fixed | Sections 3.5 and 7.1 both give ten fitted quantities. |
