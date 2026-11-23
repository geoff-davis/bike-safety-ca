# Review: age-rate-plot

## Current state

- Status: complete (accepted in round 2)
- Next action: none
- Base commit: `1b253e8`; snapshot: `/tmp/bsc-review/age-rate-plot-r1/`
- Open findings: none
- Decisions needed from the user: none

## Loop

- Loop ID and round: `age-rate-plot-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-age-plot`
- Reviewer: `bsc-reviewer` (Codex)
- Authorized scope: review requests and replies only
- Expires (UTC): 2026-11-23 02:08

## Handoff, round 1

- Tier: Medium
- Purpose: the user asked for the county hospital report's rates by age to be plotted, not only tabled. A new chart sits above the "By age group" table. It has two panels side by side, ED visits and hospital admissions per 100,000 a year, each on its own scale, with horizontal bars per age group.
- Disclosure rules, the main thing to check (`report.plotted`):
  - each age group gets the status the table uses: "published", "suppressed" or "not shown" (`withheld`);
  - a held-back group's rates are set to NaN before the chart sees them, and it is drawn only as the words "not shown";
  - a suppressed group is a pale bar over the 1-to-10-case range, which the table already prints;
  - labels use the table's decimal places (0 for visits, 1 for admissions);
  - the SVG `aria-label` lists the same values.
- `charts.by_age` is hand-drawn SVG like the existing charts, with no plotting library; `_step` picks round gridlines.
- A caption under the chart carries the CDPH credit, since the README says every chart does.
- `docs/demo/hospital_sample.pdf` (made-up counts) is regenerated.
- Tests:
  - `test_the_age_chart_draws_what_the_table_prints_and_no_more`: every printed rate appears in the chart's label, and 5–9, held back, is "not shown" in both panels;
  - `test_a_held_back_rate_never_reaches_the_chart`;
  - the credit count is 4 (one more, for the new caption), and the two chart-set assertions now include "ages".
- `make check` passed (623 tests). The real Santa Clara report rendered correctly (checked visually; data outside the snapshot).
- Please check:
  - that nothing held back can be read off the chart, including scale and gridlines, since the axis maximum comes only from drawn groups;
  - the panel geometry when a panel has only suppressed or held-back groups;
  - the `_step` edge cases.

## Review, round 1 — bsc-reviewer

- Loop: `age-rate-plot-1`, round 1.
- Reviewed `/tmp/bsc-review/age-rate-plot-r1/staged.diff`, chart helpers,
  report suppression/withholding and formatting paths, PDF insertion/style,
  new tests and text extracted from the generated synthetic sample PDF.
- Verified lock ownership (`bsc-implementer age-rate-plot`), `HERDR_ENV=1`,
  and requesting Claude identity, repository and pane `wF:p1` through Herdr.
- Disclosure review: `plotted` reuses the table's `withheld` mask, selects
  the same displayed ages and replaces held rates with NaN before passing
  them on. `by_age` excludes held rows from the maximum and does not place
  their rates in its accessible summary. Published labels use the same
  decimal places; suppressed geometry uses the source-permitted bounds.
- Independent probe: executed exact snapshot `_text`, `_step`, `_label`
  and `by_age` functions extracted through AST, using minimal row/filter/max
  stand-ins. Suppressed-only and held-only two-panel inputs produced SVG
  without non-finite coordinates; the all-zero published panel raises
  ZeroDivisionError (ARP-001). Changing held-only numeric inputs did not
  change the SVG at all. This isolates chart arithmetic, not pandas or
  browser layout integration.
- Sample: `pdftotext -layout` confirms the made-up PDF contains the new
  two-panel age chart above its table, with matching printed values and
  held groups labeled not shown. Did not visually render the PDF.
- Evidence reused: implementer's reported 623-test `make check`, added
  disclosure/credit tests and private visual rendering check. Changed Python
  files parse. No real records, protected data paths or full suite accessed.
- Verdict: **changes required, round 1**, for ARP-001. No other confirmed
  correctness findings. A verdict authorizes no commit, push or merge.

### ARP-001 — P2, blocking, confirmed: a zero-rate panel crashes the report

- Location: snapshot `src/bike_safety_ca/hospital/charts.py:171–176`.
- Concrete case: a county has no admissions in any displayed age group,
  with positive resident denominators and no hidden counts. The report's
  existing `by_age` treats absent count rows as published zeros, so its
  plotted admissions panel has `rate_low=rate_high=0` in every row.
- `_step(0)` returns a positive step, but
  `last = ceil(0 / step) * step` is still zero. Even drawing the zero
  gridline calls `x(0)`, which divides by `last` and raises ZeroDivisionError.
  A panel with held rows plus only published-zero drawable rows has the
  same failure. The exact chart-function probe reproduced the exception.
- Impact: adding the chart prevents the county report from completing for
  valid all-zero outcomes that could previously be tabled.
- Required correction: keep the axis extent strictly positive for an
  all-zero drawable panel, using a count-independent fallback or at least
  one positive step. Add a regression case for all published zeros and a
  mix of held rows and drawable zeros. Preserve the rule that held rates
  never influence the scale.
- Status: open.

## Finding ledger, round 1

| ID | Severity | Blocking | Location | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| ARP-001 | P2 | Yes | `hospital/charts.py:173` | open | Exact chart functions with a published-zero panel raise ZeroDivisionError at x(0), since axis extent is zero. |

## Handoff, round 2

- Snapshot: `/tmp/bsc-review/age-rate-plot-r2/`. Loop `age-rate-plot-1`, round 2 of 3. Expires (UTC): 2026-11-23 02:11.
- ARP-001 fixed: in `charts.by_age`, when no group is drawn, or every drawn rate is zero (or NaN), the panel's scale falls back to 0 to 1 (`if not highest > 0`).
- New test `test_a_panel_of_zero_rates_still_draws`. It builds an all-zero panel and a panel of zeros with one held-back group whose rates are NaN, then checks:
  - no "nan" or "inf" in the SVG;
  - the held-back group appears only as "not shown";
  - the zero rates are labelled "0" and "0.0";
  - each panel's scale tops out at 1.0.
- `make check` passed (624 tests).

## Review, round 2 — bsc-reviewer

- Loop: `age-rate-plot-1`, round 2.
- Reviewed `/tmp/bsc-review/age-rate-plot-r2/staged.diff`, the positive
  axis fallback and added zero-panel regression test. Reused round 1's
  disclosure, report integration, labels, credits and sample-PDF review.
- Verified lock ownership (`bsc-implementer age-rate-plot`), `HERDR_ENV=1`,
  and requesting Claude identity, repository and pane `wF:p1` through Herdr.
- ARP-001: fixed. After considering only drawable rows, the scale uses 1
  when its maximum is not positive. This keeps the denominator positive for
  published-zero and mixed held/zero panels without consulting held rates.
- Independent check: executed the exact snapshot chart helpers extracted
  through AST with minimal row/filter/max stand-ins. Zero-only and mixed
  held/zero panels produce SVG without NaN/infinity coordinates; both
  axes end at 1.0. Held-only and suppressed-only probes still pass.
  Substituting different numerical values for a held row in a mixed-zero
  panel leaves its SVG byte-identical, confirming no new scale disclosure.
- Inspected the added regression test: it checks finite output, missing
  held rates, zero labels at both decimal precisions and positive fallback
  extent. Test source parses.
- Evidence reused: implementer's reported round-2 `make check` success
  (624 tests). No full-suite, browser/PDF visual or real-data run performed;
  isolated probes do not replace pandas/rendering integration. Round 1's
  other verification limits continue to apply.
- Findings: no new correctness findings.
- Verdict: **accepted, round 2**. ARP-001 is fixed in the staged snapshot.
  This completes the review loop; acceptance authorizes no commit, push or
  merge.

## Finding ledger, round 2

| ID | Severity | Blocking | Status | Evidence |
| --- | --- | --- | --- | --- |
| ARP-001 | P2 | Resolved | fixed | Positive fallback axis; exact chart helpers pass zero-only and mixed held/zero cases, with no dependence on held rates; regression test added. |
