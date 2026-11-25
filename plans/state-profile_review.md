# Review: state-profile

## Current state

- Status: complete (loop 2, round 1 accepted)
- Next action: commit when the user approves
- Base commit: `6bb1805` (branch state-totals, PR #30, not yet merged); snapshot: `/tmp/bsc-review/state-profile-2-r1/`
- Open findings: none
- Decisions needed from the user: none

## Loop

- Loop ID and round: `state-profile-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer-2` (Claude), pane `wF:p4`, worktree `/home/geoff/Projects/personal/bike-safety-ca-state-profile`
- Reviewer: `bsc-reviewer` (Codex), pane `wF:p2`
- Authorized scope: review requests and replies only
- Expires (UTC): `2026-11-25T03:51Z`

## Handoff, round 1

- Tier: Standard
- Intended behavior and acceptance criteria: a new statewide report,
  `hospital/profile.py`, for 2023–2024, splitting hospital-treated bicycle
  injuries by age, sex, e-bike or not (cause text), and motor vehicle involved
  or not (EpiCenter mechanism "MVT-Pedal Cyclist"; the user chose this meaning
  of "traffic"). Tables: rates per 100,000 by age and sex (unique visits,
  ED and admissions, Male/Female only, Other/Unknown counted and reported as
  left out); motor-vehicle share by age and sex; e-bike share and
  motor-vehicle share for e-bikes and other bikes, by age and by sex; share
  admitted by e-bike x vehicle, all ages. Ranges for hidden cells (1 to 10);
  a sum with exactly one hidden cell among published ones prints "not shown"
  (the e-bike report's rule, applied per figure rather than by raising); a
  lone hidden cell prints its rate range marked "suppressed". Exact figures
  print as one number.
- Supporting changes:
  - `epicenter.py`: four new statewide queries (`state_total_age_sex`,
    `state_bike_mech_age_sex`, `state_bike_cause_mech_age`,
    `state_bike_cause_mech_sex`), added to `REPORT_TABLES` (now 16).
  - `population.residents(folder, by_sex=True)`: a `sex` column from the
    Census `_MALE`/`_FEM` columns; checks men + women = everyone and the
    per-sex totals (`POPEST_MALE`/`POPEST_FEM`).
  - `download/census._fetch` takes a `check` callable (default: the old
    shapefile check). `population.download` used it and always failed on
    the CSVs (bug on main); it now checks for a Census county CSV header.
  - Docs: guide and README.
- Verified on the real pulled tables by the implementer (not shared): every
  cause description maps to exactly one mechanism (0 of 125 ED, 0 of 96
  hospitalization causes with two), so crossing e-bike with vehicle by
  cause rows is exact apart from hidden cells. Sex values are Male, Female,
  Other/Unknown.
- Verification: `make check` | staged tree | lint, mypy, 655 passed | slow deselected | bsc-implementer-2
- Condition inventory:

  | Condition | Test or probe | Caught / survived / not exercised | Note |
  | --- | --- | --- | --- |
  | exact figures by hand (rates, shares, admitted) | test_the_profile_figures_match_ones_worked_out_by_hand | caught | |
  | one hidden among published -> not shown | same test (0–4 row; women 15–19) | caught | |
  | two hidden -> range | same test (women 10–14) | caught | |
  | Other/Unknown sex reported | same test | caught | |
  | missing table refused | test_the_profile_needs_its_tables | caught | |
  | residents by sex add up | test_residents_by_sex_add_up | caught | |
  | Census CSV check | test_the_census_download_keeps_only_a_county_table | caught | |
  | default pull = reports' tables | test_the_default_pull_is_exactly_the_tables_the_reports_read | caught | |

- Settled decisions (do not re-report): "traffic" = MVT mechanism (user's
  choice); no charts in this first version; shares from cause or mechanism
  rows are of coded injuries (overlap stated in Limits); "not shown" rule kept
  as in the e-bike report even though it hides the all-ages ED rates by sex.
- Known limitations and out of scope: no key-points box; no PDF sample.

## Finding ledger

| ID | Severity | Blocking | Location | Status | Evidence, fix commit, test |
| --- | --- | --- | --- | --- | --- |

## Review — state-profile-1, round 1

Verdict: **accepted, round 1**. No correctness findings in the staged change.

The profile separates unique-visit rates from coded-injury shares, uses resident-years for 2023–2024 sex/age denominators, and computes shares against the complementary category with the stated suppression bounds. The aggregation retains hidden-cell and source-cell counts for the settled not-shown rule, distinguishes absent groups from suppressed groups, and reports Other/Unknown sex outside the sex-specific rates. The e-bike/vehicle and admission outputs remain shares of coded injuries as disclosed. Population loading preserves the existing all-sex path while checking each sex's totals, their sum against everyone and complete county/year/age coverage. The downloader's custom check preserves the shapefile default and supplies a CSV check for population files.

Verification:

- Executed the actual scalar profile helpers extracted from the snapshot for worked rates/shares, one hidden cell among published cells, two hidden cells, a lone suppressed cell, empty groups and exact 0%/100% shares; all expected results pass.
- Executed the actual query-planning constants/functions: 16 default tables equal the union required by the three reports, and the full plan has 77 distinct table names. All eight new tables have statewide 2023–2024 scope, ages 0–100, on the ED and comprehensive-hospitalization tabs.
- Executed the actual Census CSV header check and population download wiring with in-memory paths: valid county headers pass, HTML/missing-column responses fail, and both population downloads receive the CSV validator. No download or file write occurred.
- Read the report aggregation, sex-specific population checks, shared download helper changes and new regression tests. Full pytest/`make check` were not independently run because NumPy, pandas and pytest are unavailable here. The handoff reports lint/types and 655 passing tests. These focused checks do not independently verify pandas joins/grouping or rendering; no PDF sample was in scope.

No protected paths or records were opened. The implementer's real-table cause/mechanism and sex-label checks were supplied context, not independently reproduced. The owner's traffic definition, coded-injury estimand and suppression rule were treated as settled.

Ledger: no findings; state-profile-1 ends accepted at round 1. Implementer releases the reviewer lock. This review does not authorize a commit, push, merge or publication.

## Loop 2

- Loop ID and round: `state-profile-2`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer-2` (Claude), pane `wF:p4`, worktree `/home/geoff/Projects/personal/bike-safety-ca-state-profile`
- Reviewer: `bsc-reviewer` (Codex), pane `wF:p2`
- Authorized scope: review requests and replies only
- Expires (UTC): `2026-11-25T19:31Z`

## Handoff — state-profile-2, round 1

- Tier: Standard. The whole staged diff against `6bb1805` is in scope; what
  changed since loop 1 (accepted, not yet committed) is listed here.
- Intended behavior, changed at the user's request:
  - The "not shown" rule is dropped in the profile and the e-bike report
    (`ebike.py` no longer raises for one hidden cell among published ones);
    such groups print as ranges. The user's reason: the rule hid figures the
    source's own tables publish (e.g. a published count next to a hidden one).
  - Charts (`charts.py`, hand-drawn SVG): `ranged()` horizontal bars, solid to
    the range's low end, paler to its high end, with a 95% chance whisker;
    `lines()` year trends with chance bands. Chance: Wilson for shares, exact
    Poisson (chi-square) for rates, each taken at the ends of the hidden-count
    range (`profile._wilson`, `_poisson`, checked against statsmodels in
    `test_the_chance_intervals_match_standard_ones`).
  - Body is charts only, tables moved to an appendix: all riders by age (new
    table `state_total_age_groups`, unique visits, any sex) then by sex; share
    admitted (admissions / (ED + admissions)) instead of admission rates;
    motor vehicle by age, both sexes together; e-bike share of ED visits plus
    admissions, described as a floor (no code says bike type unknown).
  - Trends 2016–2024 (`TREND_QUERIES` in `epicenter.py`, tables
    `state_trend_*`, span `epicenter.YEARS`); the profile includes them only
    once all four are in the manifest (not yet pulled for real).
  - Key points (`profile.key_points`): one or two bullets per chart with a bold
    lead, worked out from the figures; the leads pick wording from the ranges
    (e.g. "cannot be told apart" when two ranges overlap; "more/less often"
    only when the ratio's range is wholly above/below 1).
  - `profile.admission_ratio`: age-adjusted e-bike admission ratio, as
    `ebike.admission_ratio` but from `state_bike_cause_mech_age` summed over
    mechanism; same pairing of bounds and the same check that the pairing is a
    bound (each ordinary share x ratio < 1). Rounded to nine places before
    rounding outwards to two, so float noise is not widened.
  - Caveat bullet and Limits entry: e-bike more likely named on admitted
    records, inflating the ratio.
  - `pdf.KEPT`: a heading, then one paragraph or list, then a chart (and its
    table) are kept on one page. This applies to every report's PDF.
- Verification: `make format`, `make check` | staged tree | lint, mypy, 658 passed | slow deselected | bsc-implementer-2.
  The real report was also generated (7 pages, not shared); its ratio agrees
  with a hand calculation by the implementer.
- Condition inventory (new since loop 1):

  | Condition | Test or probe | Caught / survived / not exercised | Note |
  | --- | --- | --- | --- |
  | rates, shares, ranges by hand (all riders, by sex, vehicle, e-bike, trends) | test_the_profile_figures_match_ones_worked_out_by_hand | caught | |
  | admission ratio by hand (1.75) and its key point | same test | caught | ed/hosp unpacking swap found this way |
  | key-point wording for overlapping ranges | same test ("cannot be told apart") | caught | "more/less" branches: "more" only |
  | Wilson / Poisson intervals | test_the_chance_intervals_match_standard_ones | caught | |
  | trends left out until pulled | test_the_profile_leaves_out_trends_not_yet_pulled | caught | |
  | e-bike report mixed group gives a range | test_hospital_report e-bike test | caught | |
  | heading + list + chart kept together | test_points_between_a_heading_and_its_chart_stay_with_both | caught | |
  | admission ratio bound check raising | none | not exercised | |

- Settled decisions (do not re-report): those of loop 1, except the "not
  shown" rule, now dropped; shares of coded injuries; e-bike share is a
  floor; key points pick the highest/lowest group by the middle of its range;
  intervals treat 2023–2024 as one draw of the underlying risk.
- Known limitations and out of scope: no top-of-report key-points box; ties
  between groups go to the first in age order.

## Review — state-profile-2, round 1

Verdict: **accepted, round 1**. No blocking correctness findings in the staged scope, including the cumulative changes accepted in loop 1.

The profile retains separate unique-visit rates and coded-injury shares while replacing the earlier withholding rule as requested. Rates use resident-years, and the admission shares use admissions over admissions plus ED visits. The Wilson and exact Poisson endpoint constructions match the stated interval model. The age-adjusted admission ratio uses hospital and ED inputs in the intended order, pairs suppression bounds consistently, and checks the monotonicity condition before calling those pairings bounds. The report discloses the e-bike coding caveat and keeps the new descriptive choices separate from any claim of per-ride risk.

Trend queries use statewide 2016–2024 filters, while the existing statewide profile queries retain 2023–2024. The source checker recognizes that distinction. The profile requires all four trend manifest entries before adding the trend section, and the e-bike share is only computed for 2023 onward. The new PDF grouping rule is bounded by individual closing tags and supports the heading/list/chart structure without absorbing the next unrelated paragraph.

Focused verification (no real records):

- Executed the actual interval helpers with standard-library numerical stand-ins. Checked the 40/100 Wilson example, the exact zero-event Poisson upper limit using an independent integer-gamma inversion, and containment of all 110 combinations of one synthetic hidden-count range by the Wilson endpoint envelope.
- Executed the actual `admission_ratio` against synthetic aggregated source groups. Its returned bounds enclose all 256 endpoint combinations of a two-age example. The exact 1.75 example passes, and a constructed case violating the monotonicity condition raises the expected bound error. This exercises the guard listed as unexercised in the handoff.
- Executed the actual SVG bar and two-panel trend drawing functions with in-memory frame stand-ins: output parses as XML and has finite geometry for the tested exact/ranged figures. This is a structural check, not a visual layout or browser/PDF rendering review.
- Executed the actual PDF keep regex on heading/list/figure HTML and verified that the following paragraph remains outside the group. Executed the query planner: 20 default tables, 81 distinct full-plan tables, and correct statewide trend/non-trend spans.
- Read the result aggregation, key-point branches, source/manifest changes and regression tests. The newly cumulative population/downloader changes remain consistent with the prior accepted review.

Full pytest/`make check`, real SciPy/statsmodels integration, pandas aggregation and a rendered PDF were not independently exercised because this review environment lacks NumPy, pandas, SciPy, pytest and Markdown. The handoff reports lint/types and 658 passing tests plus a real-report check by the implementer. No protected paths or real records were opened and no download, report publication or browser agreement action was performed. The implementer's real-table coding checks and report values were supplied context, not independently reproduced. The user's revised suppression rule, coded-injury estimand, e-bike floor and midpoint-based group selection were treated as settled.

Ledger: no new findings; state-profile-2 ends accepted at round 1. Implementer releases the reviewer lock. Review does not authorize a commit, push, merge or publication.
