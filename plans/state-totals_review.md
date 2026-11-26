# Review: state-totals

## Current state

- Status: complete (round 1 accepted)
- Next action: commit when the user approves
- Base commit: `b2cd08a`; snapshot: `/tmp/bsc-review/state-totals-r1/`
- Open findings: none
- Decisions needed from the user: none

## Loop

- Loop ID and round: `state-totals-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer-2` (Claude), pane `wF:p4`, worktree `/home/geoff/Projects/personal/bike-safety-ca-state-totals`
- Reviewer: `bsc-reviewer` (Codex), pane `wF:p2`
- Authorized scope: review requests and replies only
- Expires (UTC): `2026-11-25T00:11Z`

## Handoff, round 1

- Tier: Standard
- Intended behavior and acceptance criteria: EpiCenter counts a visit once
  under each mechanism or cause it is coded with (its FAQ; CDPH confirmed by
  email, 2026-11-23). The county report's statewide rates used to add up the
  rows of the statewide cause-by-age table, so they over-counted visits coded
  under two causes. Now:
  - the downloader has a new statewide query `state_total_age_groups`
    (age summary groups, no mechanism or cause grouping: unique visits), for
    ED and comprehensive-definition hospitalizations, 2023–2024, and it is in
    the default pull (`REPORT_TABLES`, now eight tables);
  - `report.state_rates` reads `{outcome}_state_total_age_groups` through
    `rates.cells` (hidden cell = 1 to 10, so a range only if one is hidden);
  - the report prints the expected count as one figure when exact
    (`_expected`), a range otherwise, in the table and the key point;
  - the e-bike report still splits by cause (it must) but now says rows can
    overlap, and prints the cause rows' all-ages sum beside the unique visits
    (`ebike.overlap`, `_overlap`); it requires the two new tables;
  - docs (method Limits, guide, README counts), sample data and demo PDF updated.
- Changed areas and affected producers and consumers: `hospital/epicenter.py`
  (query list, REPORT_TABLES, docstring), `hospital/report.py`,
  `hospital/ebike.py`, `hospital/sample.py`, tests in
  `tests/test_hospital_report.py` and `tests/test_hospital_rates.py`.
  `tables.check_source` treats any `_state_` name as statewide, so the new
  table is checked with the same filter rules.
- Pattern inventory: every reader of `*_state_bike_cause_age_groups`:
  report.state_rates (switched), ebike.counts / admission_ratio (kept: they
  compare causes; caveat added), sample and test fixtures (unique tables added).
- Verification: `make check` | staged tree | lint, mypy, 650 passed | slow tests deselected | bsc-implementer-2
- Condition inventory:

  | Condition | Test or probe | Caught / survived / not exercised | Note |
  | --- | --- | --- | --- |
  | exact unique totals give one expected figure | test_the_figures_match_ones_worked_out_by_hand | caught | numbers redone by hand |
  | one hidden statewide group gives a range | test_a_hidden_statewide_count_makes_the_expected_count_a_range | caught | |
  | cause rows no longer affect statewide rates | test_the_statewide_rates_ignore_the_cause_rows | caught | doubles them |
  | overlap sentence | test_the_ebike_ranges_say_they_leave_chance_out | caught | |
  | default pull matches the reports' tables | test_the_default_pull_is_exactly_the_tables_the_reports_read | caught | |

- Settled decisions (do not re-report): the e-bike comparison keeps using the
  cause table (no other source distinguishes e-bikes); the old "20 to 20
  expected" expectation in test_hospital_rates is changed to "20" because an
  exact expected count now prints as one figure; the by-hand test's numbers
  change because its statewide input is now a unique-visit table.
- Known limitations and out of scope: folders pulled before this change lack
  the new tables and are refused by check_source until re-pulled with
  `--only`; a statewide breakdown by sex/traffic/e-bike is a later change.

## Finding ledger

| ID | Severity | Blocking | Location | Status | Evidence, fix commit, test |
| --- | --- | --- | --- | --- | --- |

## Review — state-totals-1, round 1

Verdict: **accepted, round 1**. No correctness findings in the staged change.

The new statewide query groups only by summary age and retains the statewide scope, bicycle/unintentional filters, 2023–2024 window and comprehensive hospitalization definition. `state_rates` now reads this unique-visit table through the existing cell-bound validation rather than aggregating cause rows. The e-bike calculations retain their cause inputs as intended, with an explicit overlap caveat and a separate cause-total/unique-total comparison. Required-table lists and the default pull agree, and the source/manifest path recognizes the new statewide table names. The expected-count formatting and revised hand-worked test expectations are consistent with the changed denominator.

Verification:

- Executed the actual query-planning constants/functions extracted from the snapshot: exactly eight default tables, exactly 69 distinct full-plan tables, correct age-only statewide query settings and ED/comprehensive-hospitalization tabs. Confirmed the union of the reports' required tables equals `REPORT_TABLES`.
- Executed the actual formatting helpers against the exact expected-count example (180), the hidden-cell range example (167 to 169), and the cause/unique overlap sentence from the new regression test; all match.
- Read the changed producers, consumers, cell-bound handling and regression tests for hidden counts and independence from cause rows. Extracted text from the synthetic sample PDF: it retains its made-up-data notice and shows a single expected count (2,308). This was a text-content check, not a visual pagination review.
- Full pytest/`make check` were not independently rerun because this review environment lacks NumPy, pandas and pytest. The handoff reports lint/types and 650 passing tests. The focused standard-library checks do not independently validate pandas integration or the numerical posterior calculations.

No real records or protected paths were opened; no external EpiCenter download or acceptance action was performed. CDPH correspondence, external FAQ claims and real statewide totals were supplied context rather than independently verified sources for this snapshot-only review.

Ledger: no findings; state-totals-1 ends accepted at round 1. Implementer releases the reviewer lock. Review does not authorize a commit, push, merge or publication.

Delivery note: the one Herdr reply attempt to bsc-implementer-2 was refused with `agent_blocked`: the implementer requires interactive input. The accepted verdict above is available through handoff polling. Snapshot deleted; reviewer lock remains for the implementer to release. User informed; no duplicate prompt sent.
