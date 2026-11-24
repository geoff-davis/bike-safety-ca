# Spread power fixed at 1: decision record and what was left

Written 23 November 2026, branch `model-review`. Aggregate figures only; no
crash records.

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
   Berkeley's in its last. The order of the list is nearly unchanged; the
   expected counts and their stated spread at the busiest corners of those
   cities are less trustworthy.

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

## Left for later

Each is a separate piece of work; none was started.

| Item | What is known | What it needs |
|---|---|---|
| Power held between 1 and 2 | One-off result above | A version in `checks.candidates`, then the same table, with the top 25 and AIC |
| Count calibration | Item 3 above; forecast level checks exist for the Los Altos study area only | Calibration by expected-count band per city, power 1 against fitted |
| Kernel density empirical Bayes (Katicha and Flintsch 2023) as an outside baseline | Only the abstract-level description has been used; the paper's text has not been read | Read the full method first. It is defined on road sections with a kernel over distance; moving it to intersections is a change to be written down, and its own handling of the local count should be kept. Then score it through `checks.candidates` on the same windows |
| Plain car term (`log(1 + car crashes)`) with a power of 1 | One-off run: −0.0014 of rank score against the fitted-power model, inside the margin | A version in `checks.candidates` |
| Street identity across cities | Streets are matched by name within an area, so two streets with one name in a pooled fit are one street | Count how often it happens in the pools; key streets by city where it does |
| Child outcomes | Few later child crashes in most cities; the child-fitted ranking does not beat the all-cyclist one anywhere | Nothing cheap; a wider area or more years |
| Unused evidence | Crashes between intersections (about a quarter) and street features are not in the model | Out of scope of this review |
| Corridors | Corner part still fits the power | Compare a power of 1 on the corridor hold-out before changing it |
