# Model review: decision record

Written 23 November 2026, branch `model-review`. Aggregate figures only; no
crash records.

## Where it ended

- **Default:** the street-length model with a spread power of 1, for the
  all-cyclist and child intersection rankings. Nothing else is selected.
- **Search closed.** After the power was fixed, a power held between 1 and
  2 and three textbook models were compared with it under margins written
  down beforehand (sections "Later comparisons" below). None replaced it.
  No further feature, power, prior, smoothing or optimiser trial is planned
  in this round.
- **Standing comparator:** textbook empirical Bayes with street context
  ("Standard empirical Bayes with street context" in `checks.candidates`).
  It is the conventional model that came closest and is kept for judging
  later changes. It is not a product option.
- **Experimental:** the jointly fitted street-effects model. Its fitting
  code was written for the comparison and has not been checked against a
  maintained package.
- **Wording:** the maps and lists show the model's estimate over the fitting
  years beside the count on record for those years. They do not show a
  count per year or a forecast, and now say so (revision `4382343`).
- **Not established:** that the model is a textbook probability model, that
  a conventional model cannot do as well, or that any difference here holds
  on new cities or years. Everything is from the development windows.

The sections from "Decision" to "Limits of the evidence" are the record of
the first step, fixing the power at 1, as written at the time; one
conclusion in it has since been withdrawn and is marked.

## Decision

The intersection rankings (all cyclists and children) are fitted with a
spread power of 1 (`SPREAD_POWER` in `model/crash_history.py`). Before, the
power was fitted in each window. `rank_intersections(..., spread_power=None)`
still fits it. The corridor table keeps the fitted power for its corner
part: it sums expected counts and was not compared.

## Evidence

- Code: revision `0b56c05`. Crash tables: built 21 November 2026 (hashes in
  the run's `run.json`).
- Command: `python -m bike_safety_ca.checks.candidates --configs config
  --processed data/processed --also los_altos=data/processed --out <folder>`.
  It writes every window unrounded (`windows.csv`), the paired summary
  (`summary.csv`) and the revision and data hashes (`run.json`).
- Windows compared: those where the reference (power fitted) was a fitted
  model and at least 30 later crashes were scored. 28 cities; the Los Altos
  study area is reported apart because it overlaps several of them.
- Margins written down before the comparison: 0.005 of rank score, and 1
  percentage point of later crashes in the top 50 and in the top 5% of
  corners.

Change from the fitted power to a power of 1 (shares in percentage points of
later crashes; the range is the 5th to 95th percentile over 10,000 draws of
whole cities, seed 20261123):

| Ranking | Windows (cities) | Rank score | Top 25 | Top 50 | Top 100 | Top 5% |
|---|---|---|---|---|---|---|
| Fitted to all cyclists, scored on all cyclists | 62 (23) | −0.0003 (−0.0007 to +0.0002) | −0.25 (−0.58 to +0.08) | +0.07 (−0.21 to +0.37) | −0.27 (−0.58 to +0.05) | +0.19 (−0.23 to +0.62) |
| Fitted to all cyclists, scored on children | 33 (17) | −0.0004 (−0.0013 to +0.0004) | −0.30 (−0.72 to +0.07) | −0.13 (−0.55 to +0.36) | −0.18 (−0.85 to +0.48) | +0.04 (−0.49 to +0.58) |
| Fitted to children, scored on children | 18 (7) | +0.0003 (−0.0002 to +0.0009) | −0.41 (−1.64 to +0.61) | −0.17 (−0.73 to +0.34) | +0.24 (−0.37 to +0.83) | −0.19 (−0.56 to +0.14) |

Leaving any one city out, the all-cyclist rank-score change stays between
−0.0004 and −0.0001. Means over cities, weighting each city once, are in
`summary.csv`; they differ in sign from the means over windows in one cell
only, the top 100 scored on children (+0.10 against −0.18).

## What it costs

Found while regenerating the documents, after the decision:

1. **Top 25.** Lower on average in all three rows, inside what a 1-point
   margin would allow but with no margin set for it. Over the 62 all-cyclist
   windows: 1,777 later crashes in the top 25 lists against 1,805. Past bike
   crashes alone now match or beat the model's top 25 in six of 27 cities
   (Berkeley, Davis, Encinitas, Menlo Park, San Diego, San Francisco); with
   the power fitted it was two.
2. **Children in the Los Altos study area.** The child-fitted ranking through
   2018 has 4 of 87 later child crashes in its top 25 (10 with the power
   fitted). Over the three windows its top 25 holds 15 of 203, the
   all-cyclist ranking's 21.
3. **Fit to the counts in large cities.** Over 64 all-cyclist windows, AIC is
   lower with a power of 1 in 32, higher by more than 2 in 28 and by more
   than 10 in nine: San Francisco (three windows, by 56 to 90), Long Beach
   (three), San Diego (two), Ventura (one). The simulation check
   (`checks.attainable`) agrees: with a power of 1, San Francisco's real
   rank score is below all 2,000 simulated scores in every window, and
   Berkeley's in its last. The order of the list is nearly unchanged.
   *Withdrawn:* this item went on to say that the expected counts at the
   busiest corners of those cities are less trustworthy with a power of 1.
   The count check below does not bear that out: in the model's own top 25
   the forecast is closer to what was recorded with a power of 1 than with
   the power fitted.

An earlier one-off run (65 windows, not the maintained command) had the
power fitted but held between 1 and 2 at +0.0002 of rank score and +0.06
points in the top 25 against the unrestricted fit. That version keeps the
estimate monotone, which was the reason for leaving the unrestricted fit,
and would fit the large cities' counts. It was not adopted because the
simpler version met the margins. Items 1 and 3 are reasons to look at it
again.

## Limits of the evidence

- These are the windows the model was developed on. Windows in a city
  overlap. The city bootstrap treats cities as independent draws from a
  population of cities, which 28 California cities are not.
- No city or period has been held back, and no ranking was frozen ahead of
  new records.
- The margins were set for the top 50 and the top 5% only.

## Later comparisons

All from `python -m bike_safety_ca.checks.candidates --configs config
--processed data/processed --also los_altos=data/processed --reference
"Spread power fitted, 1 to 2" --out <folder>` at revision `4382343`, crash
tables of 21 November 2026. The reference (H) is the model with the power
fitted between 1 and 2. Margins as before: 0.005 of rank score, 1 point in
the top 50 and the top 5%. Ranges are the 5th to 95th percentile over
10,000 draws of whole cities.

### Rankings fitted to and scored on all cyclists, 62 windows in 23 cities

Change from H:

| Model | Rank score | Top 25 | Top 50 | Top 100 | Top 5% | Cities lower |
|---|---|---|---|---|---|---|
| Power 1 (the default, B) | −0.0004 (−0.0008 to −0.0001) | −0.30 | +0.04 (−0.22 to +0.32) | −0.30 | +0.14 (−0.26 to +0.56) | 18 |
| Textbook empirical Bayes | −0.0240 (−0.0281 to −0.0204) | −1.40 | −0.76 (−1.22 to −0.30) | −1.52 | −1.24 (−1.89 to −0.59) | 23 |
| With street context | −0.0080 (−0.0104 to −0.0057) | −1.21 (−1.74 to −0.71) | −0.44 (−0.87 to −0.01) | −0.96 | −0.58 (−1.28 to +0.18) | 19 |
| Street effects, fitted jointly | −0.0107 (−0.0132 to −0.0085) | −0.45 | −0.68 (−1.42 to −0.02) | −1.12 | −0.40 (−1.02 to +0.21) | 23 |

Change from B, paired on the same windows (not a subtraction of the rows
above):

| Model | Rank score | Top 25 | Top 50 | Top 100 | Top 5% |
|---|---|---|---|---|---|
| Textbook empirical Bayes | −0.0236 (−0.0275 to −0.0200) | −1.09 | −0.80 | −1.21 | −1.38 |
| With street context | −0.0075 (−0.0099 to −0.0052) | −0.91 (−1.45 to −0.39) | −0.48 (−1.00 to +0.06) | −0.65 | −0.72 (−1.40 to −0.01) |
| Street effects, fitted jointly | −0.0103 (−0.0129 to −0.0079) | −0.15 | −0.72 | −0.82 | −0.54 |

The same against B on the 40 windows whose later period ends in 2022 (21
cities), a check that provisional 2025 and 2026 records do not drive the
result: textbook −0.0242, street context −0.0077 (−0.0105 to −0.0050),
street effects −0.0109.

Every challenger misses the rank-score margin against either reference and
on either set of windows. The street-context model meets the top-50 and
top-5% margins on the mean. It does not beat the street-effects model on
every measure: it is ahead on rank score and the top 50, behind in the top
25, the top 5% and the count deviance. No paired interval between those two
was computed.

### Rankings fitted to child crashes, scored on child crashes, 18 windows in 7 cities

Change from H:

| Model | Rank score | Top 25 | Top 50 | Top 5% |
|---|---|---|---|---|
| Power 1 | +0.0001 (−0.0003 to +0.0004) | −0.56 | −0.23 | −0.07 |
| Textbook empirical Bayes | −0.0207 (−0.0251 to −0.0159) | −1.81 | −1.53 | −1.26 |
| With street context | −0.0077 (−0.0152 to −0.0006) | −1.79 | −1.25 (−3.81 to +0.66) | −0.36 |
| Street effects, fitted jointly | −0.0416 (−0.0825 to −0.0143) | −1.49 | −2.44 | −2.19 |

A fault in the comparator was found and fixed here. Until revision
`4382343` the textbook fit was counted as failed when the Poisson fit that
only supplies its starting values did not converge, which happens when a
road class has no bike crash. Two child windows (Sacramento, fitted through
2018 and 2020) fell back to the plain count for that reason alone, each
about 0.24 of rank score below H. As first run (revision `4feaa31`) the two
textbook rows read −0.0442 and −0.0324. No all-cyclist fit was affected.
The street-effects model still fails in those two windows, in its own
fitting, and its row includes the two fallbacks; it was not investigated.

### Counts

Each model's estimate, scaled to the later period, against the crashes then
recorded; only fitted models, and only the 40 windows (21 cities) whose
later period is closed (2019–2022 or 2021–2022). Those years precede the
ones TIMS marks provisional. Whether every agency's records are complete in
the merged TIMS and CCRS table for those years was not audited.

- Totals: in every window every model's forecast total is within 0.03% of
  H's. Pooled over the windows, the crashes recorded were 79% of the
  forecast (forecast 1.26 times recorded). The windows overlap in years, so
  this is not 40 independent results, and it is a mismatch between these
  periods, not a measured trend.
- Poisson deviance per intersection, change from H (lower is better; with
  totals this close it is mainly a comparison of where the crashes are put):
  power 1 +0.0006 (+0.0001 to +0.0013); street effects +0.0065; street
  context +0.0076 (+0.0049 to +0.0103); textbook +0.0162.
- Forecast over recorded in each model's own top 25 corners: H 1.43, power 1
  1.34, textbook 1.69, street context 1.62, street effects 1.62. The lists
  differ by model; no comparison on one common set of corners was made, and
  no predictive distribution was scored.

### Power held between 1 and 2

Against the unrestricted fit, holding the power between 1 and 2 changes the
all-cyclist rank score by +0.0002 and the top 25 by +0.06 points; the
bounds bind in 13 of 113 fitted rankings. Power 1 against the held power is
the first row of the first table above. The simpler setting was kept.

## Review of the code

Each code change was reviewed by a second agent (Codex) on a snapshot with
no crash data: `plans/power-held_review.md`,
`plans/textbook-models_review.md`, `plans/street-context_review.md`,
`plans/estimate-period_review.md`. Three defects were found and fixed
there. An outside reviewer (ChatGPT) set the margins, the street-context
columns and the stop rule, and saw aggregate results only; it has not read
or rerun the code after revision `79fb6cf`.

## Left for later

Nothing here is planned. Each would be a new piece of work with its own
question.

| Item | What is known | What it needs |
|---|---|---|
| Unused confirmation data | None was set aside | A city or period not used so far, with the ranking frozen first |
| Completeness of the records by agency, 2019–2022 | Not audited; `checks.reporting` marks steps in an agency's reporting | Needed before any claim about the level of the forecast or a trend |
| A forecast figure for readers | None is shown; the forecast ran about a quarter above what was recorded in the closed periods | Its own horizon, the stated assumption that rates and recording continue, and a level check |
| Street-effects model against a maintained package | Custom approximate fit; shape at its upper limit in 10 of 88 fits; fails in two child windows | Only if that model is taken up again |
| Street identity across cities | Streets are matched by name within an area | Count how often two streets share a name in a pooled fit |
| Child outcomes | Few later child crashes in most cities; the child-fitted ranking does not beat the all-cyclist one anywhere | A wider area or more years |
| Crashes between intersections, street features | Not in the model | Out of scope of this review |
| Corridors | The corner part still fits the power | Compare a power of 1 on the corridor hold-out before changing it |
| City rankings and PDFs | Not regenerated since the power was fixed or the wording changed | Rerun the ranking and report commands for the four cities |
