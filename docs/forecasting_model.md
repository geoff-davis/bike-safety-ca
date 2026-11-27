# The intersection crash forecasting model

Status: 24 November 2026. This is the full write-up of the model that ranks
intersections by the bike crashes police are likely to record there. It
starts with how well the model does on cities it was not developed on,
against past bike crashes alone and against a model from the road-safety
literature, and how that was evaluated. The earlier tests, the fallback for
small cities, the crash records and the limits follow. The model itself,
the reason for each choice and the derivations are at the end.

Every figure is a total over many intersections, or a score; no individual
crash is described. Figures built from crash records carry the credits at
the end. [Where the ranking helps most and least](where_the_ranking_helps.md)
is the detailed companion for the city-by-city results on the development
cities, and the [guide](guide.md) says how to run each command.

**What a reader can rerun.** The crash records are not in this repository
(see "Crash records" in the guide), so no table here can be rerun from it
alone. With TIMS exports and the CCRS download, the figures of sections 1
and 2 come from one command at the revision tagged
`evaluation-final-test-run`, and the tables marked "rerun" in the later
sections from the repository's own commands at revision `88d0e04`, on the
crash tables of 21 November 2026; the command is given with each. Tables
marked "one-off" come from scripts that are not in the repository, and
those marked "not rerun" have not been repeated since the fixes of 15 to 21
November 2026 to crash placement, street names and the merge of the two
sources. "Which figures are current" lists them.

## Contents

- [Summary](#summary)
- [1. How well it performs](#1-how-well-it-performs)
- [2. How it was evaluated](#2-how-it-was-evaluated)
- [3. What is forecast](#3-what-is-forecast)
- [4. How it was tested during development](#4-how-it-was-tested-during-development)
- [5. Performance on the development cities](#5-performance-on-the-development-cities)
- [6. Cities with less data: the fallback](#6-cities-with-less-data-the-fallback)
- [7. The crash records](#7-the-crash-records)
- [8. Limits](#8-limits)
- [9. Which figures are current, and reproducing them](#9-which-figures-are-current-and-reproducing-them)
- [10. Assumptions](#10-assumptions)
- [11. The model](#11-the-model)
- [12. Why each choice was made](#12-why-each-choice-was-made)
- [Appendix: derivations](#appendix-derivations)
- [References](#references)
- [Data credits](#data-credits)

## Summary

- **On 37 cities held back from its development, the model's list finds
  more of the later bike crashes than a list of past bike crashes alone in
  every city.** Fitted on crashes through 2020 and scored on 2021–2024, it
  captures 29.3% of later bike crashes at the top of the list against 21.3%,
  a gain of 8.0 percentage points (6.8 to 9.1). A list in random order would
  capture 2.5% (section 1).
- **It is ahead of the closest model from the road-safety literature by a
  small margin.** A negative binomial regression with the empirical Bayes
  update, given the same street information, captures 28.7%: 0.6 points
  less (0.2 to 1.0); in its plain textbook form, 28.3%. Past car crashes
  alone capture 26.7%, so most of the gain over past bike crashes can be
  had from the car-crash record, and the model adds 2.6 points to that
  (1.8 to 3.4).
- **How it was evaluated.** 64 cities that played no part in building the
  model were split by a fixed rule into 22 for choosing between versions of
  the model and 42 for one final test. The measure, the margins and the two
  claims were written down first, the version was chosen on the first set,
  and the final set was scored once (section 2).
- **The gain is about the same on the cities the model was built on** (6.2
  points over the same years) **and on fatal and severe crashes alone** (8.0
  points, pooled), which are recorded more steadily than minor ones.
- **What is ranked** is the model's estimate of the number of
  police-recorded bike crashes at the corner over the years it was fitted
  on, not risk per rider. The maps and lists show that estimate beside the
  count on record for the same years. It is not a count per year, and not a
  forecast of a later period (section 3).
- **The model in one paragraph.** A corner's estimate is a weighted average
  of a background and the corner's own count. The background comes from the
  corner's car crashes, which stand in for car traffic, and the bike-crash
  record of its named streets, which stands in for bike traffic. The only
  road feature used is the number of intersections on each named street.
  The steps are not one textbook probability model: the background is built
  from the same crash histories it is then compared with. It is a
  prediction and shrinkage procedure, justified by the tests. Sections 10
  to 12 and the appendix give the assumptions, the formulas, the reason for
  each choice and the derivations.
- **Small cities.** With fewer than 100 bike crashes at intersections, or
  when the fit fails, the code uses a hand-built blend of the same inputs
  that needs no fitting. It orders intersections but gives no expected
  count. On the five held-back cities under that threshold it is 5.7 points
  ahead of past bike crashes alone. Fitting on a wider area and reading the
  ranking inside the city is the better answer; for children with under 100
  crashes, the all-cyclist ranking is used (section 6).
- **The records** are TIMS (SWITRS, injury crashes) merged with CCRS. The
  state's move from SWITRS to CCRS, and changes in how departments report,
  move counts by more than safety does. A reporting check is run before any
  comparison of years or cities (section 7).
- **What the evaluation does not show.** It covers one pair of periods,
  larger California cities and police-recorded injury crashes. The later
  years had already happened when the test was run; a ranking frozen now
  and scored on crashes not yet recorded has not been tried (section 8).

## 1. How well it performs

All figures here are from the final test of section 2: 37 cities that
played no part in building the model, each with at least 100 bike crashes
at intersections in the fitting years. Every list is built from crashes
through 2020 and scored on bike injury crashes at intersections in 2021 to
2024, 3,756 of them.

### 1.1 The measure

**Capture at the top.** Take the first $k$ intersections on a list and
count the share of the city's later bike crashes that happened at them.
The score is the average of that share over every $k$ from 1 up to 5% of
the city's intersections. It is higher when the corners with later crashes
are near the top, and highest when the worst are first: the first corner
counts toward every $k$, the last toward one. Intersections with equal
scores share their places.

- A list in random order scores about 2.5%.
- The best possible list, in order of the later crashes themselves, scores
  67% on average in these cities, not 100%: a short list cannot hold every
  corner where a crash will happen. That list needs hindsight, and much of
  where crashes fall in four years is chance, so it is a ceiling and not a
  target.
- The plain share of later crashes in the top 5% of corners is higher than
  this score, because the score also averages over the shorter lists.

The headline for a set of cities is the mean of the cities' scores, each
city counting once. Ranges in brackets are the 5th to 95th percentile over
10,000 resamplings of whole police agencies (Compton, Lancaster and Norwalk
share one, so they are drawn together).

### 1.2 Against simple lists and a model from the literature

| List | Capture at the top | Share of the best possible |
|---|---|---|
| This model | 29.3% | 43.9% |
| This model with the spread power fitted | 29.3% | 43.9% |
| Empirical Bayes regression with street context | 28.7% | 42.9% |
| Empirical Bayes regression, textbook form | 28.3% | 42.4% |
| Hand-built blend (the fallback) | 28.3% | 42.3% |
| Past car crashes alone | 26.7% | 39.6% |
| Past bike crashes alone | 21.3% | 32.4% |
| Random order | 2.5% | |

This model's lead over each, in percentage points of capture at the top:

| This model minus | Difference | Cities where this model is ahead |
|---|---|---|
| Past bike crashes alone | +8.0 (+6.8 to +9.1) | 37 of 37 |
| Past car crashes alone | +2.6 (+1.8 to +3.4) | 30 of 37 |
| Hand-built blend | +1.0 (+0.4 to +1.5) | |
| Empirical Bayes regression, textbook form | +0.9 (+0.5 to +1.4) | 25 of 37 |
| Empirical Bayes regression with street context | +0.6 (+0.2 to +1.0) | 23 of 37 |
| This model with the spread power fitted | +0.01 (−0.18 to +0.24) | |

Reading the tables:

- **Past bike crashes alone** is the list a city makes by counting. The
  model is ahead of it in every city, by 0.05 points in the closest
  (Alhambra) and by 18 in the widest (Citrus Heights). As a share of the
  best possible list the gain is 11.6 points (10.0 to 13.1).
- **Past car crashes alone** is a much stronger list than past bike
  crashes: where cars crash, bikes later do. Most of the model's gain over
  bike crashes alone is available from the car record, and what the model
  adds on top is 2.6 points.
- **Empirical Bayes regression, textbook form,** is the standard method of
  road-safety analysis: a negative binomial regression of the bike count on
  the corner's car crashes and the classes of its two main roads, followed
  by the usual update with the corner's own count (Hauer and others 2002).
  It uses standard software and no predictor built from bike crashes. The
  model is ahead by 0.9 points on average and in 25 of the 37 cities.
- **With street context** the same regression has two more columns, which
  describe the other intersections on the corner's streets. It is the
  closest standard method: the model is ahead by 0.6 points and in 23 of
  the 37 cities, so a standard method does nearly as well. Section 12.11
  describes both.
- **The spread power** makes no difference: fixing it at 1, as the model
  does, and fitting it give the same result to within 0.2 points.

Which of these were claims and which are descriptions matters. Two claims
were written down before the final test: that the model beats past bike
crashes alone, and that it is no worse than the version with the power
fitted by more than 1 point. Both were met. The comparisons with car
crashes, the blend and the two regressions were not declared beforehand
and are reported as descriptions. The textbook form was added after the
final test had been read, in a second run that reproduced every earlier
figure exactly.

Two methods from the literature were not scored on the held-back cities.
A regression with a random effect for each street was compared on the
development cities only, where it did worse than the regression with
street context (section 12.11). The kernel-smoothed empirical Bayes method
of Katicha and Flintsch (2023) has not been run on these data at all.

### 1.3 Fatal and severe crashes

Minor injuries are recorded less steadily than serious ones (section 7.3),
so the same lists were also scored on later bike crashes recorded as fatal
or severe, pooled over the 37 cities. The lists themselves are unchanged:
they are built from all injury crashes.

| This model minus | Difference, fatal or severe, pooled |
|---|---|
| Past bike crashes alone | +8.0 (+5.7 to +10.2) |
| Past car crashes alone | +2.6 (+0.9 to +4.3) |
| This model with the spread power fitted | −0.4 (−0.7 to −0.1) |

The gains are the same size as for all injury crashes. On this outcome the
fitted power is slightly ahead; on the selection cities it was slightly
behind (+0.35), so the difference is taken as noise of about a third of a
point. This result had no pass or fail attached.

### 1.4 Cities with a change in reporting, and smaller cities

- **Without flagged cities.** Four of the 37 cities are flagged by a check
  of their counts: a sharp change in minor-injury crashes between 2016–2019
  and 2021–2024, or a fall or rise in an agency's yearly injury crashes
  (section 2.5). Without them the lead over past bike crashes alone is 8.2
  points (6.9 to 9.4) and over the fitted power 0.02.
- **Smaller cities.** Five held-back cities have fewer than 100 bike
  crashes at intersections in the fitting years, so every list there is the
  hand-built blend. Pooled, it is 5.7 points ahead of past bike crashes
  alone (3.4 to 7.3) and 1.7 ahead of past car crashes alone (0.1 to 3.2).

### 1.5 The same measure on the other sets of cities

| Set | Cities | This model | Past bike crashes alone | Difference |
|---|---|---|---|---|
| Development cities | 22 | 26.8% | 20.6% | +6.2 (+4.9 to +7.5) |
| Selection set | 21 | 26.4% | 19.0% | +7.4 (+6.0 to +8.9) |
| Final test | 37 | 29.3% | 21.3% | +8.0 (+6.8 to +9.1) |

The development cities are the ones the model was built on, scored over
the same years. The model does no worse on cities it had never seen. The
levels differ between sets because the cities do, not because the model
changed.

## 2. How it was evaluated

The tests of sections 4 and 5 were run on cities and years seen while the
model was built, and the spread power was chosen on them. They cannot say
how the model does elsewhere. This evaluation was designed for that
question and fixed before any of its cities was scored. An independent
code reviewer read the plan and the code before each step.

### 2.1 The cities

- **Candidates.** California cities outside the 28 used in development,
  with at least 100 bike injury crashes on record in 2016 to 2020: 64
  cities.
- **Two sets.** Each city's Census place code is hashed with a fixed
  phrase, and the result decides the set: about a third to a **selection
  set** (22 cities), the rest to a **final-test set** (42). Cities sharing a police
  agency go together. The rule leaves no room to place a city by its results.
- **Larger and smaller.** A city counts in the headline if it has at least
  100 bike crashes at intersections in the fitting years, the same
  threshold at which the model is fitted and not its fallback: 21 of the 22
  and 37 of the 42. The others are reported apart (section 1.4).
- **Built before scoring.** All 64 were downloaded and built, and their
  counts checked, before any list was scored. Each city is scored inside
  its Census municipal limit.

### 2.2 The periods

Lists are built from crashes from 2015 through 2020 and scored on 2021 to
2024, the last year TIMS reports as final. One pair of periods is used, so
that no crash is counted in two overlapping tests.

### 2.3 The decision rule

Three versions were candidates, in order of simplicity: the regression
with street context, this model with the spread power at 1, and this model
with the power fitted between 1 and 2. A simpler version is kept unless it
is shown to be worse.

- **No worse** means the 5th percentile of the difference in capture at
  the top (simpler minus the other, city mean) is above −1 percentage
  point.
- **On the selection set:** power 1 against the fitted power first, then
  the regression against whichever was kept.
- **Before the final test** the chosen version and its comparator were
  written to a file. The scoring command will not score the final-test set
  without that file.
- **On the final-test set,** scored once, two claims: the chosen version
  beats past bike crashes alone (5th percentile of the difference above 0),
  and it is no worse than its comparator.

### 2.4 What the selection set chose

| Comparison, 21 cities | Difference | Verdict |
|---|---|---|
| Power 1 minus fitted power | +0.38 (+0.06 to +0.78) | No worse; power 1 kept |
| Regression with street context minus power 1 | −0.55 (−1.05 to −0.05) | Inconclusive; power 1 kept |

The regression was a near miss: its mean loss is inside the margin and its
lower bound 0.05 beyond it. The choice written down was this model with
the power at 1, compared with the fitted power.

### 2.5 The reporting check

Los Angeles's injury crash counts fell by more than half after 2020, almost
all of it in minor injuries, while fatal and severe counts held. A fall
like that is a change in what is recorded, and a later period recorded
differently from the fitting period is a poor test. Two checks on counts,
which read no list and no score, mark such cities:

- minor-injury crashes per year in 2021–2024 below half, or above one and a
  half times, the 2016–2019 level;
- a fall or rise in an agency's yearly injury crashes, by the check of
  section 7.4.

Flagged cities stay in the headline. The result without them is given
beside it (section 1.4). Los Angeles is in the selection set and is flagged
by both; in the final-test set Culver City is, and Alhambra, Ontario,
Santa Clara, Santa Rosa and Corona by the second alone.

### 2.6 What was fixed in advance, and what was not

- **Fixed before any held-back city was scored:** the candidates, the
  measure, the periods, the margin, the two sets, the two claims, the
  fatal-and-severe result and the reporting check.
- **Known before the sets were fixed:** Los Angeles's yearly counts by
  severity had been looked at, which is what prompted the reporting check.
  No list had been scored there.
- **Added after the selection set was scored and before the final test:**
  capture as a share of the best possible list (the second column of
  section 1.2). It is a secondary figure and enters no rule.
- **Not declared, computed afterwards:** the comparisons with past car
  crashes, the hand-built blend and the two regressions in section 1.2.
  The textbook form of the regression was not among the lists scored in
  the final test; it was added afterwards and both sets were scored a
  second time for it, with every earlier figure unchanged.
- **Not changed after any result:** the sets, the candidates, the measure
  and the rule.

### 2.7 Reproducing it

```bash
uv run python -m bike_safety_ca.checks.evaluation \
    --configs config/held_back/selection --units <units.csv> --out <folder>
uv run python -m bike_safety_ca.checks.evaluation \
    --configs config/held_back/final_test --units <units.csv> \
    --frozen <folder>/frozen.json --out <folder>
```

The configs for the 64 cities are in `config/held_back/`, and
`checks/assignment.py` holds the rule that split them. Each run writes the
cities' scores, the results, a manifest of every city (sizes, later
crashes, the two checks and a hash of its crash table) and a record of the
revision. The figures here are from the revision tagged
`evaluation-final-test-run`, and the textbook-regression row from the one
tagged `evaluation-described-lists`, on crash tables built on 24 November
2026 from TIMS exports for 2015 to June 2026 and CCRS.

## 3. What is forecast

For each intersection $i$ in an area, the model estimates the number of
police-recorded injury crashes involving a cyclist, from the crashes
recorded over a set of years. Three numbers are kept apart throughout:

- **The count on record**, $y_i$: the bike crashes recorded at the corner in
  the fitting years. A small count reflects chance as well as the road.
- **The model's estimate**, $\hat\lambda_i$ (section 11.6): the number of
  recorded bike crashes the model puts at the corner over those same years,
  from the corner's own count and what is learned from its streets. This is
  what the corners are ranked by and what the maps, lists and ranking files
  show (`expected_bike_crashes`, with the years in `first_year` and
  `last_year`). It is a total over the whole period, not a count per year.
- **A forecast for a later period** (section 11.7): the estimate scaled by
  the length of the later period. It assumes the rate and the way crashes
  are recorded stay as they were in the fitting years. It is used in this
  document's tests only; no map or list shows one.

In the code:

- A **bike crash** is an injury crash in which a bicycle was involved, after
  possible duplicate reports are removed (`crashes/groups.py`).
- A **car crash** is an injury crash with no cyclist and no pedestrian
  ("motor-vehicle-only"). Crashes with no injury are not used, because TIMS
  holds injury crashes only.
- A **child crash** is a bike crash in which any cyclist's recorded age is at
  or under `child_max_age` (18 in every config here). A crash with no
  cyclist's age recorded counts toward all cyclists but not toward children.
- A crash **at an intersection** is one placed there by the rules in
  section 7.5. Crashes between intersections are not used by this model;
  the corridor table counts them (see "Corridors" in the guide).

The quantity is a count of police records, not a risk per rider. A corner can
rank high because many people ride through it, and a count of police
records misses crashes that are not reported (most falls, and many minor
crashes). The level of the forecast is not reliable either (section 4.5);
what the model is for is the order.

## 4. How it was tested during development

### 4.1 Design

Each ranking is built from crashes up to a cut-off year and scored on bike
crashes after it (`checks/holdout.py`). Every config here uses three windows:

| Fitted on | Scored on |
|---|---|
| First year to 2018 | 2019–2022 |
| First year to 2020 | 2021–2022 |
| First year to 2022 | 2023 to the latest record (June to November 2026, by city) |

The first year is 2015 throughout (TIMS no longer offers 2014). Children are scored on later child
crashes, with rankings fitted to child crashes and, as a separate row, the
all-cyclist ranking.

What these tests are and are not:

- **Retrospective.** The later years were seen while the model was built,
  and about 100 variants were scored on the Los Altos windows. Differences of
  0.01 are within noise. The 28 cities were added after the model was first
  fixed, so their results at that point were a test on places the model had
  not seen, though in the same years. They have since been used to choose
  the spread power (section 12.2), so they are development evidence too. No
  city or period was held back from these tests; the evaluation of
  sections 1 and 2 is on cities that were.
- **Overlapping.** The second window lies inside the first, so the three are
  not independent, and sums over them are for comparison only.
- **Today's map.** Every window uses the street map of 2026, so the test asks
  how the ranking does on today's intersections, not what a ranking made in
  2018 could have known.
- **A floor of 30 later crashes.** A window with fewer later crashes in an
  area is left unscored and shows the count. A score on a handful of crashes
  is close to those crashes' own ranks. The floor limits what the test can
  show, not where the ranking can be used.

### 4.2 Measures

**Rank score.** The area under the ROC curve of the score against "had a
later crash": the chance that an intersection with a later bike crash is
ranked above one without, ties counted as half (`rank_score`; appendix A.10).
0.5 is a coin toss, 1.0 perfect. It rewards ordering the whole list, much of
it putting the many quiet corners below the busy ones, and it ignores the
level. It depends on how varied a city's streets are and on how its crashes
are spread among them, so it is not comparable across cities. By the
Hanley–McNeil formula, one standard error at a score of 0.8 is about 0.08
with 10 intersections that had a later crash and about 0.05 with 30.

**Later crashes at the top-ranked intersections.** Later bike crashes at the
25, 50 and 100 highest-ranked intersections, ties at the cut sharing the
places (`top_share`). This is closer to "where to look first", but a fixed
top 100 is 1% of Fresno's intersections and 36% of East Palo Alto's.

**Forecast level and spread.** The forecast of section 11.7 against the
counts that happened, by groups of intersections, and the ratio of summed
squared errors to summed forecast variance (section 4.5).

### 4.3 Results for Los Altos, fitted with its neighbours

Los Altos alone has too few bike crashes for the model to be fitted, so it
is fitted together with five whole neighbouring cities (Cupertino, Los
Altos Hills, Mountain View, Palo Alto and Sunnyvale) and read inside its
own limit: 6,470 intersections, 805 of them in Los Altos. Later bike
crashes in the three windows: 458, 189 and 340 (children 144, 57 and 106).
Rerun:
`python -m bike_safety_ca.checks.holdout --config config/los_altos.yaml`.

Until 26 November 2026 the Los Altos results came from a smaller study
area, two-mile circles around ten public schools plus the city limit
(4,208 intersections, from 2014). That area has been retired. Wherever a
later section says "study area", the figure was fitted on it by a one-off
script and has not been rerun on the six cities.

Mean rank score over the three windows, all six cities:

| Ranking | All cyclists | Children |
|---|---|---|
| Past bike crashes | 0.687 | 0.605 |
| Bike + car crashes, added | 0.768 | 0.740 |
| Hand-built blend (`street_blend_score`) | 0.822 | 0.795 |
| Earlier fitted formula (`fit_history_model`) | 0.829 | 0.809 |
| **Street-length model** (`fit_street_model`) | **0.844** | **0.825** |
| All-cyclist model, scored on child crashes | | 0.818 |

By window, street-length model:

| | 2019–2022 | 2021–2022 | 2023 on |
|---|---|---|---|
| All cyclists, six cities | 0.848 | 0.838 | 0.845 |
| Children, six cities | 0.837 | 0.830 | 0.807 |
| All cyclists, inside Los Altos | 0.858 | too few (22) | 0.840 |

Inside the Los Altos city limit the middle window has 22 later crashes and
is left unscored; the mean over the other two is 0.849 for all cyclists,
against 0.680 for past bike crashes alone. No window has 30 later child
crashes there (18, 9 and 19).

Later crashes at the highest-ranked intersections of the six cities, summed
over the three windows (top 25 / 50 / 100; from the same command's `--out`
file; ties share their places, and counts are rounded):

| Ranking | All cyclists (of 987) | Children (of 307) |
|---|---|---|
| Past bike crashes | 50 / 86 / 152 | 15 / 28 / 40 |
| Bike + car crashes, added | 50 / 97 / 176 | 9 / 24 / 41 |
| Hand-built blend | 49 / 104 / 192 | 11 / 26 / 43 |
| Earlier fitted formula | 61 / 114 / 183 | 20 / 29 / 43 |
| Street-length model | 50 / 97 / 188 | 10 / 24 / 44 |
| All-cyclist model, on child crashes | | 9 / 24 / 51 |

In the top 25 and top 50 the model is no better than past bike crashes
alone here, and the earlier fitted formula is ahead of it; the model's gain
is from the top 100 down, and in the rank score, which is mostly about
ordering the many corners with little or no crash record. The same was true
on the former study area. Three figures from that area have not been rerun
on the six cities: the share of later crashes at corners with no earlier
crash, the comparison with the road-and-traffic model of the original Los
Altos analysis (level with this model for all cyclists, 0.856 against
0.857), and the resampling ranges.

### 4.4 The tests on many cities

The same windows were run on 28 cities and four pooled areas (section 5).
The cities were added after the model was first fixed. One choice has since
been made on them, the spread power (section 12.2); they are retrospective
tests, one run per city.

### 4.5 Forecast level and spread

Study area, the two windows before 2023. Rerun, same script as section 11.9.

**Level.** Carried forward at the fitting years' rate, the forecast is too
high: 359 against 261 recorded for all cyclists in 2019–2022, and 170
against 114 in 2021–2022 (children: 139 against 87, and 63 against 40).
Recorded crashes per year fell after the fitting years, partly in 2020 and
partly through reporting (section 7.3). A model of where crashes happen
cannot know that, and no forecast of the level is offered.

**Spread.** With the level set to the actual total, intersections grouped
by forecast rank; forecast ± one standard deviation, then recorded:

| Rank band | All cyclists, 2019–22 | All cyclists, 2021–22 | Children, 2019–22 | Children, 2021–22 |
|---|---|---|---|---|
| Top 25 | 33 ± 6, 24 | 14 ± 4, 17 | 9 ± 3, 4 | 4 ± 2, 5 |
| 26–100 | 48 ± 7, 49 | 21 ± 5, 15 | 14 ± 4, 16 | 7 ± 3, 3 |
| 101–400 | 82 ± 9, 75 | 36 ± 6, 35 | 25 ± 5, 25 | 12 ± 4, 10 |
| The other 3,808 | 98 ± 10, 113 | 43 ± 7, 47 | 38 ± 6, 42 | 17 ± 4, 22 |

The top 25 of the child ranking fitted through 2018 had 4 later crashes
where 9 were forecast, and the corners below the top 400 had more than
forecast in all four columns.

**Variance.** Summed squared errors divided by summed forecast variance are
0.94 to 1.06 (1 means the squared errors add up to the stated variances
over all intersections together; errors of opposite sign in different
groups can cancel in it). For all
cyclists in 2019–2022 the model expected 210 intersections with at least
one later crash and 39 with two or more; 216 and 39 had them.

Both checks are made after setting the level to the actual total, so they
test how the forecast shares crashes among intersections, not the total.
They take the fitted street averages and parameters as known. They show the
spread is of the right size over many intersections; they do not show that
the stated uncertainty for any one intersection is right.

## 5. Performance on the development cities

The ranking was run on 28 cities and four pooled areas, each with the
windows of section 4.1. Crash records are TIMS exports for 2015 to June
2026 merged with CCRS; streets are from OpenStreetMap and city limits from
the Census Bureau. Each city is scored over all the intersections it was
fitted on. The tables of sections 5.1 and 5.5 are rerun at revision
`88d0e04`, with crashes at the edge of each area counted (section 7.5):

```bash
uv run python -m bike_safety_ca.checks.cities --configs config --pool 'pool_*' los_altos --out output/cities
```

The run took about six minutes.
[The companion note](where_the_ranking_helps.md) discusses each city, on
the same run. Against the run of 21 November 2026, before crashes at the
edge were counted, scores differ by a few thousandths (Davis and Palo Alto
by 0.004).

### 5.1 Results by city

All cyclists unless marked. Means are over the windows scored (30 or more
later crashes). "Fit" says whether the model was fitted in every window, in
some ("mixed"), or the blend was used throughout. "Top 100" is later bike
crashes at the 100 highest-ranked intersections, summed over the windows
scored, for the model and for past bike crashes alone.

| City | Intersections | Windows scored | Rank score | Past bike crashes alone | Fit | Top 100: model / past, of all later | Children (windows scored) |
|---|---|---|---|---|---|---|---|
| Irvine | 4,983 | 3 | 0.903 | 0.678 | model | 161 / 130 of 493 | 0.895 (3) |
| Huntington Beach | 3,571 | 3 | 0.895 | 0.683 | model | 357 / 288 of 905 | 0.880 (3) |
| San Jose | 14,136 | 3 | 0.891 | 0.676 | model | 353 / 242 of 1,842 | 0.832 (3) |
| Sacramento | 10,292 | 3 | 0.889 | 0.670 | model | 223 / 168 of 1,445 | 0.834 (3) |
| Chico | 2,313 | 3 | 0.884 | 0.637 | model | 94 / 60 of 197 | too few |
| Cupertino | 990 | 2 | 0.880 | 0.703 | mixed | 68 / 54 of 102 | too few |
| San Diego | 19,467 | 3 | 0.880 | 0.652 | model | 250 / 212 of 2,442 | 0.816 (3) |
| South Lake Tahoe | 820 | 1 | 0.876 | 0.529 | blend | 37 / 9 of 55 | too few |
| Davis | 1,114 | 3 | 0.876 | 0.766 | model | 141 / 130 of 235 | too few |
| Ventura | 2,261 | 3 | 0.873 | 0.667 | model | 192 / 163 of 469 | 0.832 (1) |
| Encinitas | 1,299 | 3 | 0.872 | 0.659 | mixed | 90 / 69 of 178 | 0.805 (1) |
| Palo Alto | 1,288 | 2 | 0.871 | 0.742 | model | 82 / 72 of 175 | 0.816 (1) |
| Sunnyvale | 1,989 | 3 | 0.865 | 0.666 | model | 109 / 74 of 256 | too few |
| Long Beach | 5,151 | 3 | 0.863 | 0.702 | model | 330 / 315 of 1,546 | 0.777 (3) |
| Santa Barbara | 1,594 | 3 | 0.863 | 0.703 | model | 250 / 216 of 628 | 0.813 (2) |
| Oakland | 5,667 | 3 | 0.861 | 0.689 | model | 214 / 165 of 1,024 | 0.758 (2) |
| Fresno | 11,648 | 3 | 0.861 | 0.552 | mixed | 73 / 52 of 540 | 0.795 (1) |
| San Francisco | 7,094 | 3 | 0.854 | 0.744 | model | 749 / 696 of 3,638 | 0.752 (2) |
| Santa Cruz | 1,108 | 3 | 0.837 | 0.719 | model | 189 / 174 of 384 | 0.794 (1) |
| Redwood City | 1,397 | 3 | 0.835 | 0.630 | model | 112 / 88 of 276 | 0.783 (1) |
| Mountain View | 1,030 | 3 | 0.830 | 0.658 | model | 132 / 92 of 244 | 0.775 (1) |
| Los Altos (alone) | 806 | 2 | 0.818 | 0.678 | blend | 40 / 32 of 73 | too few |
| San Mateo | 1,519 | 2 | 0.804 | 0.570 | blend | 48 / 30 of 139 | too few |
| Menlo Park | 675 | 3 | 0.801 | 0.682 | mixed | 111 / 100 of 176 | 0.734 (1) |
| Berkeley | 1,437 | 3 | 0.792 | 0.686 | model | 241 / 234 of 796 | 0.742 (2) |
| Santa Monica | 895 | 3 | 0.783 | 0.670 | model | 144 / 119 of 352 | too few |
| East Palo Alto | 279 | 2 | 0.743 | 0.618 | blend | 53 / 42 of 71 | too few |
| Los Altos Hills | 372 | 0 | too few | too few | blend | – | too few |

In summary:

| | Cities | Rank score, model | Rank score, past bike crashes alone |
|---|---|---|---|
| Scored, all cyclists | 27 | 0.743 to 0.903, median 0.863 | 0.529 to 0.766 |
| Scored for children | 18 | 0.734 to 0.895 | |
| Model fitted in every window | 19 | | |

- The model beats past bike crashes alone in every city scored, on both
  measures.
- Scores are not comparable across cities (section 4.2), and many rest on
  few later crashes. No intervals were computed for this table.
- Santa Monica's police have no injury crash on record for 2020, so its
  windows are tested and fitted with a year missing (section 7.3). Fresno,
  Palo Alto, San Mateo and South Lake Tahoe have reporting changes inside
  the fitting or test years.
- The companion note discusses where the model helps most (spread-out
  cities built on arterials, and corners with no bike crash on record) and
  least (Berkeley, where cycling may be separated from car traffic; cities
  where history is already rich; the very top of the list; very small
  cities).

### 5.2 Corners with no bike crash on record

Most intersections have no bike crash in the fitting years, yet many later
crashes happen at them, and past bike crashes cannot order them at all.
Over the 74 windows scored in 27 cities (one-off script calling
`rank_intersections` on the hold-out's inputs, rerun at `88d0e04`):

| | Range over windows | Median |
|---|---|---|
| Share of intersections with no bike crash in the fitting years | 71% to 99% | |
| Share of later bike crashes that happened at them | 27% to 93% | 53% |
| Model's rank score among them alone | 0.66 to 0.90 | 0.83 |

The highest shares are in Fresno (80% to 93%), San Mateo (77% to 86%) and
South Lake Tahoe (93%, one window), where police reporting was far below
normal for part of the fitting years (section 7.3), so the "history" has
gaps. Without those three the share runs from 27% (San Francisco) to 72%.

This replaces the figure of "a quarter to 70%" in twelve cities, from an
earlier run, that the README and the companion note used to quote.

### 5.3 Car crashes alone

How well car crashes alone rank later bike crashes says how far a city's
bike crashes follow car traffic. Mean over the windows scored, same one-off
script:

| City | Car crashes alone | Model |
|---|---|---|
| San Jose | 0.819 | 0.891 |
| Sacramento | 0.812 | 0.889 |
| Chico | 0.809 | 0.884 |
| Huntington Beach | 0.809 | 0.895 |
| Ventura | 0.795 | 0.873 |
| Davis | 0.694 | 0.876 |
| Berkeley | 0.689 | 0.792 |
| San Mateo | 0.682 | 0.804 |
| East Palo Alto | 0.677 | 0.743 |
| Fresno | 0.673 | 0.861 |
| Los Altos (alone) | 0.664 | 0.818 |
| Menlo Park | 0.664 | 0.801 |

The first five are the highest car-only scores of the 27 cities, the last
seven the lowest. Over the 74 city-windows the model's score and the car-only
score have a correlation of 0.65. (The companion note's 0.84 was over ten
cities and two windows, from an earlier run.) Davis and Fresno are the clear
exceptions: there the street terms and the corner's own record do most of
the work.

### 5.4 Does the score look like the model's own simulations?

A simulation draws later crashes from the fitted model's own rates and
scores the model's ranking on them; the mean is the score the ranking would
expect if the model were exactly right about the city. It is a check of the
model against itself, not a ceiling on what any ranking could score: risk
the model misses is missing from its simulations too. The check is
`python -m bike_safety_ca.checks.attainable`. Its nine-city table, rerun at
revision `88d0e04`, is in the companion note. Most of
Berkeley's distance from the other cities is what the model's own rates
predict (simulated means about 0.08 below Huntington Beach's), with a real
score about 0.03 short of that on average. San Francisco's real score is
0.02 to 0.03 below its simulated mean in every window and below all but a
few of its 2,000 simulations (four at most): with the power fixed at 1 the model takes its risk to be
more concentrated at the busiest corners than the later crashes were
(section 12.2).

### 5.5 With and without minor crashes

Departments differ in how many "complaint of pain" crashes they file
(section 7.3), so the ranking was built twice per window, from all injury
crashes and from crashes with a visible injury or worse (bike and car
crashes alike), and each scored on later cyclist crashes of both kinds.
Rerun, from the cross-city command. Over the 72 windows in 27 cities with
30 later crashes of both kinds:

| Mean rank score on later cyclist crashes | Trained on all injury crashes | Trained on visible injury and worse |
|---|---|---|
| All injury crashes | 0.855 | 0.841 |
| Visible injury and worse | 0.850 | 0.837 |

The ranking without minor crashes is worse in 69 of the 72 windows on all
later crashes and in 68 on the visible-and-worse ones. Part of the loss is
the fallback: without minor crashes a city sooner has under 100 bike crashes,
and in 8 windows only that ranking fell back to the blend (loss 0.035). In
the 54 windows (21 cities) where both came from a fitted model, it loses
0.011 and 0.010, and is worse in 53 and 51 of them. Minor crashes help find
where later serious ones happen, and the ranking keeps them.

## 6. Cities with less data: the fallback

### 6.1 When the code falls back

`rank_intersections` uses the hand-built blend in place of the model when

- the area has fewer than 100 bike crashes at intersections in the fitting
  years (`MIN_CRASHES`), counted for the outcome being ranked (all cyclists,
  or children); or
- the fit raises an error (the optimiser did not converge, or a value error
  or floating-point error in the fit); or
- the fit returns an estimate that is not finite at some intersection.

The ranking file and the hold-out table say which method was used, and the
ranking file gives the reason (`fallback_reason`).

**Why 100.** On made-up cities, where the true rates are known, the fitted
model ranks the true rates better above roughly 100 bike crashes, and the
blend does as well or better below about 50 (docstring of
`rank_intersections`; the study behind it is not in the repository). The
default sits between. Below it, ten fitted numbers rest on too few crashes,
and the fit either fails or overfits.

### 6.2 What it falls back to

The hand-built blend `street_blend_score` needs no fitting:

$$
\text{score}_i = \Bigl(1 + \frac{y_i + \bar y_i}{2}\Bigr)
\Bigl(1 + \frac{x_i + 0.5\,\bar x_i}{1.5}\Bigr),
$$

where $\bar y_i$ and $\bar x_i$ are the mean bike and car counts along the
corner's streets, each street's mean taken over all its corners **including
this one**, and averaged (not summed) over the corner's streets; a corner on
no named street uses its own count. It is a product of a bike term and a car
term, as the model is, with the corner and its streets blended at fixed
weights (1 for the bike street mean, 0.5 for the car one, because car crashes
are more numerous and need less help from the street). It orders
intersections; it is not an expected count, so the ranking file leaves
`expected_bike_crashes` empty and no forecast is possible.

How it compares where both can be run: 0.822 against 0.844 for the model on
Los Altos and its five neighbours (section 4.3), and 0.82 to 0.83 for no-fit versions of the
model's product. Where the model cannot be fitted it is what is left; the
better answer is usually to fit on a wider area.

### 6.3 Pooling with neighbours

A small city does not have to fall back. Fit the model on the city together
with its neighbours, then read the ranking inside the city. The Los Altos
config (`config/los_altos.yaml`) and the pooled configs
(`config/pool_*.yaml`) do it with whole neighbouring cities in one county.
The cross-city command fits each pool as a whole and scores it inside the
limit of every member city, beside that city's score when fitted alone. A
city is a member when at least 95% of its limit lies inside the pool's area.

Mean rank score inside the city over the windows scored (rerun, cross-city
command). The Santa Clara County cities are shown in the pool without San
Jose; "too few" means no window had 30 later crashes.

| City | Pool | All cyclists, alone | Pooled | Children, alone | Pooled |
|---|---|---|---|---|---|
| Berkeley | Berkeley and Oakland | 0.792 | 0.789 | 0.742 | 0.779 |
| Oakland | Berkeley and Oakland | 0.861 | 0.859 | 0.758 | 0.750 |
| East Palo Alto | San Mateo County cities | 0.743 | 0.773 | too few | too few |
| Menlo Park | San Mateo County cities | 0.801 | 0.798 | 0.734 | 0.790 |
| Redwood City | San Mateo County cities | 0.835 | 0.839 | 0.783 | 0.787 |
| Cupertino | Santa Clara County cities | 0.880 | 0.899 | too few | too few |
| Los Altos | Santa Clara County cities | 0.818 | 0.849 | too few | too few |
| Los Altos Hills | Santa Clara County cities | too few | too few | too few | too few |
| Mountain View | Santa Clara County cities | 0.830 | 0.826 | 0.775 | 0.814 |
| Palo Alto | Santa Clara County cities | 0.870 | 0.866 | 0.816 | 0.832 |
| Sunnyvale | Santa Clara County cities | 0.865 | 0.865 | too few | too few |

- The cities that fell back to the blend in some or all windows when alone
  gain: Los Altos by 0.031, East Palo Alto by 0.030 and Cupertino by 0.019.
  Menlo Park, fitted in some windows alone, is the exception (down 0.003).
- Cities that fit the model alone are unchanged, within 0.005 either way.
- A bigger pool is not better: adding San Jose to the six Santa Clara County
  cities moves none of them by more than 0.005 (Palo Alto, 0.866 to
  0.861).
- Pooling does not fix a city whose trouble is not sample size (Berkeley).
- Los Altos Hills has too few later crashes to be scored either way. That
  is a limit of the test, not a reason against pooling it.
- No intervals were computed, and no difference here has been shown to be
  outside the noise.

Two cautions. Pool with cities that resemble yours: South Lake Tahoe has no
such neighbour. And a pool mixes police departments, so a change in one
department's reporting distorts the ranking across the pool: its corners
keep their past crashes but record few new ones, so they sit above corners
elsewhere that go on to have crashes. In the Los Altos case study, widening
the area to the whole of the neighbouring cities lowered the score for 2023
onwards from 0.886 to 0.837, almost all of it outside the original study
area, where Palo Alto's police record almost no crashes after 2022 (see
"Changes in police reporting" in
[the case study](case_study_los_altos.md#changes-in-police-reporting)).
Run the reporting check on the pool, and score or publish inside each city.
A pool cannot yet cross a county line. "Setting up a pool" in the companion
note gives the steps.

### 6.4 Child rankings

In the Los Altos study area 37% to 39% of bike crashes in the fitting years
involve a cyclist of known age 18 or under, so a child ranking has well
under half the crashes of the all-cyclist one, and more often too few to
fit. Two shortages are easy to confuse.

**Too few later crashes to score.** This limits the test, not the ranking.
Inside the Los Altos city limit the windows hold 18, 9 and 18 later child
crashes, so the city has no child score of its own. The child score of
the six cities it is fitted with (0.825, on 144, 57 and 106) is a result
for those six cities; how well the ranking orders corners inside Los
Altos for children is not known.

**Too few child crashes to build a child ranking from.** This is about the
fitting years. Each hold-out has an "All-cyclist ranking" row for children:
the ranking fitted to every cyclist crash, scored on later child crashes.
Over the 34 city-windows with 30 or more later child crashes, from the 28
cities fitted alone (rerun, cross-city command):

| Child crashes in the fitting years | City-windows (cities) | Ranking fitted to child crashes | All-cyclist ranking | Child ranking better in |
|---|---|---|---|---|
| Under 100 | 16 (13) | 0.786 | 0.806 | 0 |
| 100 or more | 18 (7) | 0.833 | 0.835 | 10 |

Under 100 child crashes, where the model cannot be fitted and the child
ranking is the blend, it loses to the all-cyclist ranking every time. At
100 or more the two are level. In Los Altos and its five neighbours, with
227 to 371 child crashes in the fitting years, they are 0.825 and 0.818.
Nowhere in these cities does a separate child ranking clearly beat the
all-cyclist one. At the top of the list the two are level there: they
hold 10 and 9 of the 307 later child crashes in their top 25 (section 4.3).

So the code and the guide follow these rules:

- `python -m bike_safety_ca.model --children` refuses to build a child
  ranking from fewer than 100 child crashes at intersections, and says to
  use the all-cyclist ranking, fit on a wider area, or pass `--force`
  (which builds the blend).
- The hold-out prints, under its table, "too few crashes to fit … rank this
  group by the all-cyclist ranking instead" for each such window.
- Fit wide and report inside the city: a pool of neighbouring cities gives
  the fit enough child crashes. Pooling raised child scores in five of the six
  cities where one could be scored both ways, each on one or two windows.
- Where the all-cyclist ranking is used for children, say so. A missing
  child ranking is not a finding of no risk to children.

## 7. The crash records

The model is only as good as the police records it is fitted to. This
section says where they come from, what the state's change of records system
does to them, how reporting by departments changes, how crashes are put on
the map, and what the reporting check finds. Tables marked "rerun" come from
one-off scripts over the 28 cities' crash tables of 21 November 2026, at
revision `c87bd4e`, using the repository's own loading and checking
functions; they print totals only. Years run from 2015 to the latest record
(June to November 2026, by city); 2026 is unfinished everywhere.

### 7.1 Two sources: TIMS and CCRS

| | TIMS | CCRS |
|---|---|---|
| Published by | SafeTREC, University of California, Berkeley, from the state's crash records | California Highway Patrol, on data.ca.gov |
| How it is got | Exports made by hand with a free account (`Crashes.csv`, `Parties.csv`, `Victims.csv`) | Downloaded by the code (`python -m bike_safety_ca.crashes download`), one file per year and table |
| Crashes held | Injury crashes only (fatal and injury) | Every reported crash, property damage only included |
| Years read here | 2015 to the export (TIMS no longer offers 2014) | From 2016 |
| Timeliness | Months behind | Updated monthly; later reports and corrections keep arriving |
| Coordinates | Geocoded by SafeTREC where it could | As recorded on the report; some early years tens of kilometres off |
| Cause | Vehicle Code section and cause category | Section only; the merge infers the category |
| Injury grade | Crash severity 1 to 4, victim degree of injury | Extent of injury per person, in the newer grades (section 7.2) |
| Terms | Credit asked; not an official record; litigation limits | Public domain; no credit asked |

TIMS is the primary source. Every TIMS crash is kept with its own values,
and CCRS adds what TIMS lacks: crashes after the TIMS export, the few
injury crashes TIMS does not have, and coordinates where TIMS has none
(`crashes/merge.py`). Property-damage-only crashes from CCRS are kept in the
tables but not used by the model or the reporting check, which use injury
crashes only so that the two sources are compared like for like. Building
from CCRS alone is not supported yet.

### 7.2 The change from SWITRS to CCRS

CCRS is the Highway Patrol's database that replaced SWITRS, and it now feeds
TIMS. Local departments moved to filing through it at different times. The
change touches the records in four ways.

**Case numbers.** A TIMS case number of eight digits starting with 8 is "8"
plus the CCRS Collision Id of a report filed through CCRS by local police;
one starting with 9 is "9" plus the Collision Id of a Highway Patrol or
sheriff's report. Older reports have seven-digit SWITRS numbers. TIMS does
not document this; it is read from the numbers. The merge links TIMS crashes
to CCRS reports directly by these numbers when the crash dates agree within
a day, and otherwise by agency, date, time within 20 minutes, and a shared
street name or points within 150 m. Rerun, all 28 cities pooled:

| Year | Injury crashes | TIMS case numbers in the CCRS style | TIMS crashes linked by case number | Linked by date, time and place | Not linked | In CCRS only |
|---|---|---|---|---|---|---|
| 2015 | 30,883 | 0.0% | 0% | 0% | 100% | 0 |
| 2016 | 32,343 | 0.0% | 29% | 70% | 0.3% | 35 |
| 2017 | 31,569 | 0.0% | 30% | 70% | 0.3% | 32 |
| 2018 | 31,941 | 0.0% | 29% | 71% | 0.4% | 44 |
| 2019 | 31,682 | 0.5% | 29% | 71% | 0.4% | 46 |
| 2020 | 23,339 | 4.2% | 29% | 70% | 0.8% | 67 |
| 2021 | 28,027 | 7.6% | 34% | 66% | 0.7% | 114 |
| 2022 | 29,071 | 13.1% | 39% | 60% | 0.7% | 147 |
| 2023 | 29,636 | 21.2% | 48% | 52% | 0.6% | 400 |
| 2024 | 30,175 | 22.0% | 49% | 51% | 0.6% | 224 |
| 2025 | 29,483 | 21.7% | 50% | 49% | 0.9% | 385 |
| 2026 (part) | 23,539 | 21.7% | 55% | 44% | 1.7% | 10,078 |

"Injury crashes" are after removing possible duplicate reports. The CCRS
files read here start in 2016, so no 2015 crash can be linked. Before 2019
the links by case number are the Highway Patrol's and sheriffs' 9-numbers;
the rise after 2019 is local departments moving to CCRS. Of the 47 agencies
in these cities with 50 or more injury crashes a year, 14 have CCRS-style
numbers by mid-2026, the first from the second quarter of 2019 and the last
from the third quarter of 2025; the rest file no reports in that style.

**Timeliness.** TIMS lags CCRS. Before 2023 a few dozen injury crashes a
year in these cities are in CCRS only; in the unfinished 2026, 43% are. The
last test window therefore leans on CCRS for its latest months. Records
found only in CCRS often lack a cyclist's age, so they count toward all
cyclists but not children.

**Injury grades.** CCRS records each injured person as "suspected serious
injury", "suspected minor injury" or "possible injury", in place of SWITRS's
"severe", "other visible" and "complaint of pain". The merge maps them to
the TIMS crash severities 2, 3 and 4. TIMS carries the newer grades for
reports filed through CCRS. Share of injured people at each grade, all 28
cities pooled (rerun):

| Year | Killed | Severe | Other visible | Complaint of pain | Suspected serious | Suspected minor | Possible injury |
|---|---|---|---|---|---|---|---|
| 2015 | 1.0% | 3.9% | 24.5% | 70.6% | 0% | 0% | 0% |
| 2017 | 1.0% | 3.8% | 22.3% | 64.6% | 0.5% | 2.6% | 5.3% |
| 2018 | 1.0% | 3.0% | 16.6% | 43.5% | 1.8% | 12.4% | 21.7% |
| 2020 | 1.5% | 3.5% | 17.8% | 42.9% | 2.4% | 11.7% | 20.1% |
| 2022 | 1.5% | 2.8% | 14.4% | 34.1% | 3.3% | 17.5% | 26.4% |
| 2023 | 1.3% | 1.9% | 9.6% | 24.7% | 4.0% | 23.2% | 35.3% |
| 2024 | 1.2% | 1.9% | 9.1% | 23.7% | 4.2% | 23.4% | 36.4% |
| 2025 | 1.0% | 1.2% | 5.4% | 14.3% | 4.5% | 35.8% | 37.8% |
| 2026 (part) | 0.5% | 0.9% | 3.6% | 8.5% | 4.7% | 41.6% | 40.1% |

The newer grades appear from 2017, earlier than CCRS-style case numbers,
and by 2026 they are more than four-fifths of injured people (86%). Whether "suspected
minor injury" covers exactly what "other visible injury" did has not been
checked. The crash severities change with them (section 7.3), so severity
counts are not comparable across an agency's change of system.

**Reporting through the change.** A change of records system is when a
department is most likely to stop filing some reports, or file them under
another agency's code. The Los Altos case study shows both: from 2023 some
Los Altos police reports carry the Palo Alto police code (the Los Altos
config moves them back with `agency_reassignments`), and Palo Alto police
reports nearly stop after 2022, at about the time its reports change format.
The reporting check's chart of reports per quarter by case-number style
shows, agency by agency, whether volume carried over.

**Duplicates.** The merge flags, and leaves out of every count, a CCRS
report resubmitted under a new Collision Id, two TIMS crashes linked to one
CCRS report, the same crash reported by two agencies (same date, times
within 15 minutes, same street pair or within 100 m), and two reports of
one crash from one agency (within 2 minutes and 100 m, with the same
parties). Nothing is dropped; the pairs are written out for checking. The
guide lists the rules in full ("Building the crash tables").

### 7.3 Changes in police reporting

A ranking built from police reports reads a fall in reports as a fall in
crashes. Three kinds of change matter for the model.

**A department whose reporting falls or stops.** Its corners keep their past
crashes but record few new ones. The fitting years then overstate them
against the test years, and in a pooled area its corners sit above corners
elsewhere that go on to have crashes. Agency-years marked as a fall in
injury crashes by the reporting check (rerun, `reporting.diagnose` on each
city; agency codes as on the reports):

| City | Agency | Years marked "fall" | Crashes in those years | Typical year |
|---|---|---|---|---|
| Fresno | 1005 (police) | 2016–2019 | 171, 47, 21, 192 | 1,132 |
| Palo Alto | 4312 (police) | 2023–2025 | 8, 29, 16 | 188 |
| Sacramento | 9250 (highway patrol) | 2025, 2026 to 9 November | 58, 42 | 170 |
| San Jose | 9725 (highway patrol) | 2023–2025, 2026 to 11 November | 16, 13, 6, 4 | 54 |
| San Mateo | 4116 (police) | 2015, 2016, 2022 | 6, 13, 78 | 237 |
| Santa Monica | 1965 (police) | 2020 | 0 | 441 |
| Los Altos (alone) | 4305 (police) | 2024, 2026 to 27 October | 15, 14 | 63 |

South Lake Tahoe police (0902) are marked as a rise in 2022–2025 (70 to 82
against a typical 22). Los Altos police's 2025 (33) is marked a possible
fall; the case study finds the same fall, almost all of it in "complaint of
pain" reports. These Los Altos figures need the config's
`agency_reassignments` rule, which moves the department's reports filed
under Palo Alto's code from 2023 back to it: without the rule every year
from 2024 reads as zero. Santa Monica's 2020 is a real gap in the
records: CCRS holds 8 crashes of any kind under that department's code in
2020, against 864 in 2019 and 891 in 2021 (from the companion note). None of
these has been confirmed with a department.

The "typical year" here is the yearly check's trimmed median over all
years. After a long collapse it can settle between the old and new levels:
Palo Alto police's 188 compares with about 350 a year before 2022 in the
level-step table below, and Sacramento highway patrol's 170 with about 280
before 2020. This is one of the check's known weaknesses (section 7.4,
issue #1); the falls are real either way.

**Minor-injury reports falling while totals hold.** A department can stop
filing its least serious crashes, or grade them differently, with no fall
in its total large enough to flag. Across the 28 cities the share of injury
crashes graded "complaint of pain" falls steadily (rerun, all 28 cities
pooled):

| Year | Injury crashes | Complaint of pain | Visible injury | Serious injury | Fatal |
|---|---|---|---|---|---|
| 2015 | 30,883 | 64.7% | 29.2% | 4.9% | 1.3% |
| 2016 | 32,343 | 66.0% | 27.7% | 5.0% | 1.3% |
| 2017 | 31,569 | 63.9% | 29.6% | 5.2% | 1.3% |
| 2018 | 31,941 | 59.8% | 33.1% | 5.8% | 1.2% |
| 2019 | 31,682 | 60.1% | 32.3% | 6.3% | 1.3% |
| 2020 | 23,339 | 56.9% | 34.0% | 7.2% | 1.9% |
| 2021 | 28,027 | 55.4% | 35.0% | 7.7% | 1.8% |
| 2022 | 29,071 | 54.1% | 36.6% | 7.4% | 1.9% |
| 2023 | 29,636 | 54.5% | 36.6% | 7.3% | 1.6% |
| 2024 | 30,175 | 54.7% | 36.3% | 7.5% | 1.5% |
| 2025 | 29,483 | 47.2% | 44.4% | 7.1% | 1.3% |
| 2026 (part) | 23,539 | 44.4% | 47.9% | 7.0% | 0.7% |

Some of this may be real. Some is not: the jump in 2025 comes mostly from
San Diego, where the share graded visible rose from 34% to 62%, and San
Jose, from 31% to 45%, with little change in most other cities. The
reporting check's table of lasting changes of level (section 7.4) finds the
agency-level steps. Over 2015 to 2025, 19 of the 28 cities have at least one
agency with a step, 26 agencies in all (rerun, cross-city command):

| Measure | Fewer reports | Regraded | More reports |
|---|---|---|---|
| All injury crashes | 5 | – | 3 |
| Complaint of pain | 14 | 4 | 2 |
| Visible injury | 2 | 3 | 3 |
| Serious injury | 0 | 0 | 6 |

"Regraded" means the agency's other severities changed the opposite way by
a half to twice as much, so the crashes are probably still reported at
another grade. The steps in "complaint of pain" crashes (typical year before
→ after; rerun):

| Agency | From | Complaint of pain | Other severities | Read as |
|---|---|---|---|---|
| Menlo Park police (4109) | 2018 | 110 → 23 | 62 → 93 | fewer reports |
| Redwood City police (4113) | 2018 | 222 → 53 | 105 → 167 | fewer reports |
| Berkeley, highway patrol (9370) | 2018 | 105 → 59 | 31 → 34 | fewer reports |
| Santa Monica, highway patrol (9565) | 2018 | 87 → 46 | 27 → 29 | fewer reports |
| Berkeley police (0103) | 2019 | 333 → 103 | 200 → 411 | regraded |
| Ventura police (5608) | 2019 | 329 → 162 | 210 → 328 | regraded |
| Santa Cruz police (4402) | 2019 | 120 → 38 | 132 → 99 | fewer reports |
| Cupertino, sheriff (4300) | 2019 | 86 → 34 | 49 → 42 | fewer reports |
| Davis police (5701) | 2020 | 45 → 20 | 69 → 108 | regraded |
| Irvine police (3026) | 2020 | 376 → 179 | 231 → 262 | fewer reports |
| Encinitas, highway patrol (9650) | 2020 | 71 → 40 | 31 → 28 | fewer reports |
| Cupertino, highway patrol (9340) | 2020 | 62 → 36 | 29 → 20 | fewer reports |
| Sacramento, highway patrol (9250) | 2020 | 178 → 55 | 102 → 41 | fewer reports |
| Mountain View police (4311) | 2022 | 120 → 32 | 94 → 145 | regraded |
| Palo Alto police (4312) | 2022 | 222 → 6 | 127 → 17 | fewer reports |
| San Jose, highway patrol (9725) | 2022 | 27 → 8 | 22 → 7 | fewer reports |
| Chico police (0402) | 2023 | 107 → 40 | 130 → 121 | fewer reports |
| Los Altos police (4305) | 2023 | 35 → 1 | 35 → 32 | fewer reports |

Only five of these 18 agencies have a step in their total, so the yearly
flags on totals miss most of them. In Menlo Park and Redwood City the other
severities rise by about a third of the fall, under the half the table calls
regrading, so those are probably a mix. 2020 is a year when crashes really
fell, and none of these steps has been confirmed with a department.

**What this does to the model.** Two things. Counts are not comparable
across a step, between years or between cities, and a ranking pooled over
cities gives more weight to the ones that file more minor crashes. But
leaving minor crashes out does not help the ranking (section 5.5), so it
keeps them. Where an agency's reporting falls, score and publish inside
each city, and keep its flagged years out of any before-and-after
comparison.

### 7.4 The reporting check

`python -m bike_safety_ca.checks.reporting --config <city>` is run before
comparing years or cities, and before trusting a pooled ranking. It counts
injury crashes and cyclist injury crashes per reporting agency and year,
after duplicate reports are removed (`checks/reporting.py`,
`crashes/tims.py`).

**Yearly flags.** Each agency-year is compared with the agency's own typical
year: the median of its finished years, recomputed leaving out years under
0.6 of it or over 1/0.6 times it until the set settles, so a gap of several
years does not drag the level toward itself. The other agencies can only
excuse a move, never cause a mark (appendix A.12).

| `change` | The year's count is |
|---|---|
| `fall` | under 0.4 of the typical year |
| `rise` | over 2.5 times it |
| `possible fall`, `possible rise` | under 0.6 of it, or over 1.67 times |

A mark also needs a typical year of 20 injury crashes (8 cyclist crashes)
and a count that a Poisson count around the expected number would give less
than once in a thousand. An unfinished last year is judged against the part
of the year up to the last crash date, and rises are not marked in it.

Agency-years marked in the 28 cities, over 2015 to the latest record (rerun):

| Measure | Fall | Possible fall | Possible rise | Rise |
|---|---|---|---|---|
| Injury crashes | 19 | 16 | 9 | 4 |
| Cyclist injury crashes | 15 | 13 | 7 | 0 |

For cyclist crashes 2020 is marked in nine agency-years (three falls),
because in most cities the other agencies have too few cyclist crashes to
show that the fall was shared.

**Lasting changes of level** (`level_steps.csv`). An agency whose yearly
count settles at a new level, under 0.6 of the old one or over 1.67 times
it, with at least three finished years on each side, at most one of them on
the wrong side of the midpoint between the levels, and 20 crashes a year on
the higher side. It looks in all injury crashes and at each severity, and
for a step at one severity says whether the other severities took it up
(`regraded`) or not (`fewer reports`, `more reports`). Section 7.3 gives
what it finds.

**Two pictures.** Reports per quarter by case-number style, which shows when
each agency moved to CCRS and whether its volume carried over; and injury
crashes per year by severity, which shows regrading.

**What it does not catch.** From the companion note and issue #1:

- A lasting step smaller than the lines: Santa Cruz police settle in 2018 at
  about 0.6 of their earlier level, and no single year is marked as a fall
  (the level table lists it).
- A steady decline is marked at one end or both, depending on where the
  median falls; after a long collapse the ordinary years before it can be
  marked "possible rise" (Palo Alto police 2015–2019, issue #1).
- A real fall with no one to compare with: in a city where one agency files
  nearly everything, a region-wide year such as 2020 can be marked.
- The unfinished last year can be marked "possible fall" when its latest
  months are thin as well as short (Long Beach and Oakland in 2026, issue
  #1).
- A gap that opens and closes again may give no lasting step (San Mateo
  police, 2015–2016 and 2021–2022).
- A department that files under another agency's code looks like a fall in
  one and a rise in the other, unless the config moves the reports back.

A flag is a question for the department, not proof that reporting changed.

### 7.5 Placing crashes on the map

**Where the point comes from.** Share of injury crashes by the source of
their point (rerun):

| Point from | All 28 cities | Range over cities |
|---|---|---|
| TIMS (geocoded by SafeTREC) | 91.9% | 79.7% (East Palo Alto) to 97.1% (Berkeley) |
| CCRS, for a crash TIMS lacks or could not geocode | 3.3% | 0.9% to 8.6% |
| Recovered from the street names on the report | 1.9% | 0.1% to 11.4% (East Palo Alto) |
| No usable point | 2.9% | 0.3% to 7.0% (East Palo Alto) |

**Recovery from street names** (`crashes/locate.py`, `merge.place_unlocated`).
A crash with no point, or with a CCRS point over 1 km from both streets its
report names, is placed from the report's primary road, cross street,
distance and direction. TIMS points are kept as given. The names are looked
up in a county road-centerline layer if one is given, otherwise in the
OpenStreetMap street table (every city here used the street table). Names
are compared with directions and street types dropped, within the report's
own city only.

1. The corner is where the two named roads cross at exactly one place in
   the city. Several crossings all within 60 m of each other (a divided
   road, or two) are taken as one corner and averaged; crossings further
   apart are ambiguous and the crash is left unplaced. Roads that do not cross
   but pass within 15 m are joined at the midpoint of the gap.
2. With a distance and a compass direction, the crash is moved that far
   along whichever named road runs that way, up to 500 feet. With a
   distance but no direction, it stays at the corner and is marked; such a
   crash counts at the intersection only if the distance is 35 m or less.
3. A second, looser pass takes cross streets that stop up to 60 m short of
   the primary road, offsets up to 1,000 feet, and roads within 60 degrees
   of the reported direction.

The commonest reasons a crash cannot be placed are a road name not found
among the city's streets and an offset longer than the limit.

**At which intersection** (`network/junctions.py`). Intersections are the
OpenStreetMap nodes where three or more street arms meet; nodes within 25 m
are one intersection, and the two halves of a divided road's crossing are
joined when they share street names and lie within 60 m. A crash counts at
an intersection if

- it lies within 35 m of it; or
- the report codes it as at the intersection (or within 50 feet) of two
  streets that both meet there, and it lies within 100 m. A name match
  wins over the nearest intersection.

Nearness does not count when the report names two streets and neither
meets at that intersection: that describes somewhere else, such as a
freeway above a surface street or a wrong point, and the next nearest
intersection within 35 m that it could describe is tried. Crashes at no
intersection are not used by this model.

**Crashes at the edge of the area (changed 26 November 2026).** Crashes
used to be cut to the area's outline before being placed, so a corner a few
metres inside a city limit lost every report whose point fell on the other
side of the line. A crash recorded up to 100 m outside the outline now
counts at an intersection inside it by the rules above, unless an
intersection beyond the outline fits it better. This adds about 1% to the
crashes placed across the held-back cities, next to nothing in some (11
crashes in San Francisco) and more where busy corners lie on the limit (6%
in Davis). The figures that repository commands produce on the development cities
were rerun with it (section 9 lists which); the rest were computed before
the change. Sections 1 and 2 keep the figures of the final test as it was
run. That evaluation was run again with the change, with the same frozen
choice and nothing re-chosen:

| | Before | After |
|---|---|---|
| Final test, model against past bike crashes (37 cities) | +7.96 (+6.79 to +9.14) | +7.98 (+6.81 to +9.19) |
| Final test, model against the fitted-power version | +0.01 (−0.18 to +0.24) | +0.01 (−0.18 to +0.24) |
| Final test, model's capture at the top | 29.26 | 29.21 |
| Final test, ahead of past bike crashes in | 37 of 37 | 37 of 37 |
| Selection cities, model against past bike crashes (21 cities) | +7.43 (+6.00 to +8.89) | +7.15 (+5.80 to +8.54) |
| Selection cities, model against the fitted-power version | +0.38 (+0.06 to +0.78) | +0.36 (+0.05 to +0.76) |

Both claims stand unchanged. On the final-test cities the other
all-injury comparisons of section 1 move by less than 0.1 point. The
fatal-and-serious comparisons move more: from +8.00 to +8.13 against past
bike crashes, from +2.62 to +2.87 against past car crashes, and from −0.39
(−0.73 to −0.10) to −0.31 (−0.66 to 0.00) against the fitted-power
version. No city changes between the larger and
smaller groups, and none changes between a fitted model and the fallback.

Share of located cyclist injury crashes counted at an intersection, from
each city's first year to the latest record (rerun, one-off script calling
`build_junctions` and `assign_crashes` on each city):

| | Share at an intersection | Without the street-name check |
|---|---|---|
| All 28 cities pooled (31,261 crashes) | 78.3% | |
| Median over cities | 74.7% | 75.3% |
| Lowest | Los Altos Hills 56.8%, Cupertino 62.9%, Huntington Beach 65.7% | |
| Highest | Oakland 89.5%, Berkeley 85.5%, San Jose 85.1% | |

The crashes are those located inside the city's outline, with those just
outside it that are counted at an intersection inside. Without the latter
the pooled share is 78.2% of 31,134, as before the edge rule.
The street-name check moves under one point in most cities, at most 3.3
points (Huntington Beach). Cities of long blocks and arterials, and hilly
ones with few intersections, have more crashes between corners, which this
model does not rank; `bike_safety_ca.model.corridors` ranks street
segments.

These rules were checked with the sensitivity command
(`python -m bike_safety_ca.checks.sensitivity`), which reruns the hold-out
with one placement choice changed at a time; a result that moves a lot under
them is not robust. Unplaced crashes are a risk if they cluster: if a
street's crashes are often reported in a way that cannot be placed, that
street is under-ranked. This has not been examined.

## 8. Limits

- **Police records, not crashes.** The model ranks where police record bike
  injury crashes. Unreported crashes, most falls among them, are not seen,
  and a department's reporting habits are part of what it learns (section
  7.3).
- **Counts, not risk.** A corner ranks high because many people ride
  through it as well as because it is dangerous for each of them. No
  measure of exposure is used.
- **One held-back test, on years already past.** The evaluation of
  sections 1 and 2 is on cities the model was not developed on, with one
  pair of periods (through 2020, then 2021–2024), in larger California
  cities. Every other test is on cities and years seen during development.
  A forward test, with a ranking frozen now and scored on crashes not yet
  recorded, has not been done.
- **Scores are not comparable across cities**, and most city scores rest on
  one to three overlapping windows with no interval computed.
- **The level is not forecast.** Totals fell after the fitting years in the
  study area; the forecast is useful for ordering and for the relative
  spread, not for the number of crashes next year.
- **Corners are treated as independent in the fit** (assumption 11), so the
  log-likelihood comparisons in section 12 are comparisons of fit, not
  tests, and the forecast variance of a group total is somewhat too small.
- **One street map for all years.** Changes to streets during the period are
  not seen. Neither are changes made after a crash, which the model reads as
  continuing risk.
- **Crashes between intersections are left out**, a quarter of located bike
  crashes in the median city (section 7.5).
- **Small cities** fall back to the blend, which gives no expected count,
  unless fitted with neighbours. A pool cannot cross a county line yet.
- **Children.** No city here gains from a separate child ranking (section
  6.4); the all-cyclist ranking is used for children where there are fewer
  than 100 child crashes, and the choice should be stated.
- **The spread power is fixed at 1 for the rankings** (section 12.2). The
  order barely differs from the one with the power fitted, but the top 25 is
  slightly worse on average, and in San Francisco, Long Beach and San Diego
  the counts fit clearly worse, so expected counts at their busiest corners
  should be read with more caution than the ranks.
- **Figures not rerun.** Section 12 and parts of sections 4 and 5 rest on
  one-off runs from before the fixes of 15 to 21 November 2026 (section 9).

## 9. Which figures are current, and reproducing them

Every figure that depends on the model was rerun with the spread power at 1,
at revision `3ae2f89` or later; the figures on the crash records (section 7)
are from revision `c87bd4e`. All are on the crash tables built on 21 November
2026 from TIMS exports (2015 to June 2026, 2014 for the study area) and CCRS
(2016 to November 2026).

The figures of sections 1 and 2 are from
`python -m bike_safety_ca.checks.evaluation` at the revision tagged
`evaluation-final-test-run` (section 2.7), on the held-back cities' crash
tables built on 24 November 2026.

**Rerun with repository commands** at revision `88d0e04`, which counts a
crash recorded just outside an area's outline at its corner inside (section
7.5). The yearly flags are as they were: that check places no crash. In the two lists below this table, sections 5.2, 5.3 and 7.5 (share at
an intersection) were rerun at the same revision with a rewritten script;
everything else there predates that rule:

| Section | Figures | Command |
|---|---|---|
| 12.2 | Spread power 1 against the fitted power, all cities | `python -m bike_safety_ca.checks.candidates --configs config --out <folder>` |
| 4.3 | Los Altos rank scores, fitted with its neighbours, by window, top 25/50/100 | `python -m bike_safety_ca.checks.holdout --config config/los_altos.yaml --out <file>` |
| 5.1, 5.5, 6.3, 6.4, 7.3 (level steps) | City table, severity sensitivity, pooled table, child table, level-step counts and table | `python -m bike_safety_ca.checks.cities --configs config --pool 'pool_*' los_altos --out <folder>` (about six minutes) |
| 5.4 (companion table) | Simulated against real rank scores, nine cities | `python -m bike_safety_ca.checks.attainable --config config/<city>.yaml`, per city |
| 7.3, 7.4 (yearly flags) | Falls and rises, counts of marks | `python -m bike_safety_ca.checks.reporting --config config/<city>.yaml`, per city |

**Rerun with one-off scripts** (not in the repository; each calls the
repository's own functions and prints totals only):

- 12.2 (AIC by window): `fit_street_model` with the power fitted and fixed,
  per city and window.
- 11.9, 12.4 (the $Q$ table), 4.3 (corners with no crash), 4.5: fits of
  `fit_street_model` and `forecast` on the hold-out's inputs for the study
  area.
- 5.2, 5.3: `rank_intersections` and `rank_score` per city and window.
- 7.2, 7.3 (severity shares), 7.5 (point sources): tables of the merged
  crash files and `reporting.report_format`, all 28 cities pooled.
- 7.5 (share at an intersection): `build_junctions` and `assign_crashes` per
  city.

**Not rerun since the fixes of 15 to 21 November 2026**, kept with that
label where they appear:

- 12.3: rank correlations of 0.72 and 0.59 with measured car volume.
- 12.4: the street-length powers $n^{0.7}$, $n^{0.6}$ and $n^{0.84}$, and the
  car-pull comparison.
- 12.5: the AIC gap of 30 to 50 between sum and mean over streets.
- 12.6 and 12.7: the tables of what each choice contributes and of road and
  traffic information.
- 12.8: the tried-and-dropped list, including 0.82 to 0.83 for no-fit
  products.
- 12.9: the fitted powers of the earlier formula.
- 4.3: the road-and-traffic row and the resampling ranges.
- 5.3: the correlation of 0.84 quoted from the companion note.

Earlier figures that this note replaces: "a quarter to 70%" of later crashes
at corners with no bike crash, in twelve cities (now 27% to 93%, median 53%,
over 27 cities, section 5.2); the top-ranked counts "of 586" and "of 204"
(now of 593 and of 203); the study-area log-likelihoods of about −1454 to
−1422 by pull (now −1439 to −1404); and the level of 358 against 263 (now
359 against 261).

## 10. Assumptions

Each assumption is listed with what follows if it fails. Sections 11 and 12
show where each is used.

1. **Counts are Poisson given the rate.** Bike crashes at intersection $i$
   over the fitting years are $y_i \mid \lambda_i \sim
   \text{Poisson}(\lambda_i)$, independently given the rates. Standard for
   crash counts.
2. **Rates vary around an expectation, as a gamma distribution.** Corners
   with the same surroundings do not share one rate:
   $\lambda_i \sim \text{Gamma}$ with mean $\mu_i$ and shape $s_i$, so that
   counts are negative binomial with variance
   $\mu_i + \alpha\,\mu_i^{p}$. The rankings fix the power at $p = 1$
   (section 12.2); 2 is the textbook case. If the true spread of rates has another shape, the blend in
   section 11.6 is still a reasonable weighting but no longer the exact
   posterior mean.
3. **The bike-crash rate is a product of powers of traffic.**
   $\lambda^{\text{bike}} = c\,V^{a}B^{b}$ with car flow $V$ and bike flow
   $B$, and car crashes $\lambda^{\text{car}} \propto V^{q}$. This is the
   usual form of intersection crash models (Highway Safety Manual, Part C)
   and of "safety in numbers" work (Jacobsen 2003; Elvik and Bjørnskau
   2017).
4. **A corner's car-crash record stands in for its car traffic.** This
   follows from assumption 3 if car crashes are recorded alike across the
   area. The record also carries street design and reporting, so it is a
   predictor of bike crashes, not a measurement of traffic. Where one department stops filing some reports, its corners' car
   terms are too low (section 7.3).
5. **Bike traffic is similar along a named street.** Riders travel along
   streets, so the bike crashes at a street's other corners stand in for
   the bike flow at this one. A corner on two streets takes riders from both,
   so its two streets' figures are added. Where riding is concentrated on
   a different set of streets from car traffic (the Berkeley reading in
   [the companion note](where_the_ranking_helps.md#where-it-helps-least)),
   this works less well.
6. **What is typical for a street depends on its length.** The expected
   bike crashes per corner of a named street with $n$ intersections is a
   power of $n$, $t(n) = e^{\beta_0} n^{\beta_1}$. Long named streets are
   the through routes.
7. **Rates are steady over time up to a common factor.** The ranking needs
   only the relative rates to carry over from the fitting years to the
   later ones. The overall level is not assumed to carry over, and in the
   tests it did not (section 4.5).
8. **Reporting is uniform across the area and over the years.** A crash is
   equally likely to be recorded wherever and whenever it happens. This is
   the weakest assumption: section 7.3 shows departments whose reporting
   falls or changes, and a pooled ranking is distorted by it.
9. **Crashes are placed correctly.** Each crash is put at the right
   intersection, or at none. Section 7.5 gives the rules and how many
   crashes cannot be placed.
10. **The street map applies to every year.** Intersections and street
    names are today's OpenStreetMap, used for all years. A corner rebuilt
    or renamed in the period is treated as unchanged.
11. **For fitting, corners are treated as independent.** They are not:
    corners on one street share a street average, and each corner's count
    is in its neighbours' averages. The likelihood is used as a fitting
    criterion and to compare fits, not for standard errors or formal tests.

## 11. The model

The code is `fit_street_model` in `src/bike_safety_ca/model/crash_history.py`,
called through `rank_intersections`, which falls back to the blend of
section 6 when there are too few crashes. The steps below follow the code.

### 11.1 Notation

| Symbol | Meaning |
|---|---|
| $y_i$ | Bike crashes at intersection $i$ in the fitting years (or child crashes, for the child ranking) |
| $x_i$ | Car crashes at $i$ in the same years |
| $R(i)$ | The named streets that meet at $i$ (by `street_key`: the name with its street type, so Park Avenue and Park Place are two streets) |
| $n_r$ | Number of intersections in the area on street $r$ |
| $Y_r$ | Bike crashes summed over the intersections on street $r$ |
| $t(n)$, $t^{\text{car}}(n)$ | Typical bike (car) crashes per corner on a street with $n$ intersections |
| $Q$, $Q^{\text{car}}$ | Strength of the pull toward $t(n)$: 20 for bike crashes, 1 for car crashes |
| $\mu_i$ | The model's expectation for $i$ before its own bike count is used |
| $p$, $\alpha$ | Spread power and scale: variance $\mu + \alpha\mu^{p}$ |
| $s_i$ | Gamma shape at $i$: $s_i = \mu_i^{2-p}/\alpha$ |

### 11.2 Typical value for a street of a given length

For each named street $r$, the total $Y_r$ is fitted by Poisson regression
on $\log n_r$ with offset $\log n_r$:

$$
\log E[Y_r] = \log n_r + \beta_0 + \beta_1 \log n_r,
$$

so the typical value per corner is

$$
t(n) = e^{\beta_0}\, n^{\beta_1}.
$$

The fit is on every named street in the area, each corner's count included
(`street_length_average`). An intersection with no named street is given
$t(1) = e^{\beta_0}$ in place of a street average. The same is done for car
crashes, giving $t^{\text{car}}(n)$.

### 11.3 Street averages, leaving the corner out (blend A)

For a corner $i$ on street $r$, the street's average is taken over its other
corners, pulled toward the typical value by $Q$ imaginary corners:

$$
\bar m_{r,-i} = \frac{(Y_r - y_i) + Q\,t(n_r)}{(n_r - 1) + Q}.
$$

A corner's street bike term is the **sum** over its streets:

$$
m_i = \sum_{r \in R(i)} \bar m_{r,-i}.
$$

$Q = 20$ (the argument `pull`). It is not fitted in each run; it was chosen
on the fitting years (section 12.4).

### 11.4 The car term (blend B)

The street car average $m^{\text{car}}_i$ is built the same way from car
counts, with $Q^{\text{car}} = 1$ (`car_pull`). The corner's own car count
is then blended with it as a gamma-Poisson posterior mean, with one shape
$k$ for all corners, fitted by maximum likelihood to the car counts as
negative binomial around $m^{\text{car}}_i$ (`fit_shape`):

$$
\tilde x_i = \frac{k + x_i}{k/m^{\text{car}}_i + 1}.
$$

Unlike blend A, the corner's own count is in it: car crashes are only a
predictor of bike crashes, so using them does not put the same number on
both sides of the fit.

### 11.5 The expectation and the fit

$$
\mu_i = \exp\bigl(\gamma_0 + b\log m_i + a\log\tilde x_i\bigr)
= e^{\gamma_0}\, m_i^{\,b}\, \tilde x_i^{\,a}.
$$

The bike counts are negative binomial around $\mu_i$ with variance
$\mu_i + \alpha\mu_i^{p}$, that is with gamma shape
$s_i = \mu_i^{2-p}/\alpha$. For a given $p$, $(\gamma_0, b, a, \alpha)$ are
fitted by maximum likelihood (L-BFGS-B, started from two values of $\alpha$,
keeping the better; a failure to converge raises an error, and the fallback
is used). The rankings set $p = 1$ (`SPREAD_POWER`; section 12.2). Asked to
fit it (`spread_power=None`), the code chooses $p$ by a one-dimensional
search over $[0.5, 2.5]$ that maximises the profile log-likelihood
(`_fit_spread`).

The fitted numbers are $\gamma_0$, $b$, $a$, $\alpha$, the car shape $k$,
and the two pairs $(\beta_0, \beta_1)$ for the typical values: nine in
all, with $p$, $Q$ and $Q^{\text{car}}$ set beforehand.

### 11.6 The corner's own count, and what is ranked (blend C)

The estimate the intersections are ranked by is the posterior mean of the
corner's rate given its own count:

$$
\hat\lambda_i = E[\lambda_i \mid y_i]
= \frac{s_i + y_i}{s_i/\mu_i + 1}
= w_i\,\mu_i + (1 - w_i)\,y_i,
\qquad w_i = \frac{s_i}{s_i + \mu_i}.
$$

With the rankings' $p = 1$ the shape is $s_i = \mu_i/\alpha$, and the
weight is the same at every corner of one fit:

$$
\hat\lambda_i = \frac{\mu_i + \alpha\,y_i}{1 + \alpha}
= (1 - u)\,\mu_i + u\,y_i, \qquad u = \frac{\alpha}{1 + \alpha}.
$$

Both $\mu_i$ and $y_i$ are counts over the fitting years. For example, with
a background of 0.5 crashes, two crashes on record and $u = 0.4$, the
estimate is $0.6 \times 0.5 + 0.4 \times 2 = 1.1$. The weight is fitted, so
it differs between cities and between fitting periods.

In plain terms the model does three things. It estimates a background
number of crashes for the corner from its streets and its car crashes
(sections 11.2 to 11.5). It combines that background with the corner's own
count, by the weighted average above. And it ranks the corners by the
result. A corner with no crash on record is not put at zero, and a corner
with one bad stretch is not taken at face value.

Only this last step is a textbook calculation. The background is itself
built from crash counts, including those of the neighbouring corners whose
own estimates use this corner's count in turn, so the steps together are
not a single probability model with one likelihood. They are a procedure
whose worth rests on the tests in sections 4 and 5, and nothing here says
that a street's traffic or design causes the crashes.

The last step is the empirical Bayes estimate used in road safety to correct
regression to the mean (Hauer 1997). It is a plug-in estimate: $\mu_i$ and
$\alpha$ are fitted to the same crashes and then treated as known
(assumption 11). It is the column `eb` in the fit, the
`score` the ranking writes, and `expected_bike_crashes` in the ranking file:
an estimated count over the whole of the fitting years.

### 11.7 Forecast for a later period

After the fit the rate at $i$ is gamma with shape $s_i + y_i$ and rate
$s_i/\mu_i + 1$. The count in a later period $r$ times as long as the
fitting period is negative binomial with

$$
\text{mean}_i = r\,\frac{s_i + y_i}{s_i/\mu_i + 1}, \qquad
\text{variance}_i = \text{mean}_i + r^2\,\frac{s_i + y_i}{(s_i/\mu_i + 1)^2}.
$$

`forecast` returns both. The forecast carries the fitting years' rate
forward unchanged: it assumes that neither the rate nor the way crashes are
recorded changes, and no trend is fitted. In the closed test periods the
crashes recorded were about a fifth fewer than forecast (section 12.11),
so the level should not be relied on. Summing variances over a group of intersections
treats the fitted street averages and parameters as known and the corners
as independent, so the spread of a group total is somewhat understated.

### 11.8 The three blends side by side

The model pulls a noisy number toward a steadier one in three places. They
are not the same operation, and the differences are deliberate.

| | A. Street bike average | B. Corner's car crashes | C. Corner's bike crashes |
|---|---|---|---|
| What is noisy | Bike crashes at the street's other corners | The corner's own car count | The corner's own bike count |
| Pulled toward | $t(n)$ for a street with that many intersections | The street car average (itself pulled toward $t^{\text{car}}(n)$) | The fitted expectation $\mu_i$ |
| Corner's own count in it? | No | Yes | Yes |
| Strength | $Q = 20$ imaginary corners | Street average: $Q^{\text{car}} = 1$. Blend: one gamma shape, about 0.25 | Shape $\mu_i/\alpha$ (the case $p = 1$) |
| Role | A predictor in $\mu_i$ | A predictor in $\mu_i$ | The estimate ranked by |
| Code | `street_length_average(bike, streets, pull)` | `street_length_average(car, streets, car_pull)`, `fit_shape`, `gamma_blend` | `gamma_blend` with `prior_shape` |

What each does to a corner with no record: A gives a corner on a street with
no bike crash the typical value for a street of that length, which is low
for short streets. B gives a corner with no car crash a small positive car
term set by its street. C leaves a corner with no bike crash a little below
its expectation, at $\mu_i\,s_i/(s_i + \mu_i)$.

### 11.9 Fitted values

Los Altos study area (4,208 intersections), fitted on 2014 to the year shown
with $p = 1$. The last column is the power the fit chooses when asked to.
Rerun: one-off script calling `fit_street_model` on the hold-out's inputs,
revision `3ae2f89`.

| Fitted on | Bike crashes | Street bike power $b$ | Car power $a$ | $\alpha$ | Weight on own count $u$ | Car shape $k$ | $p$ if fitted |
|---|---|---|---|---|---|---|---|
| All cyclists, 2014–2018 | 449 | 1.49 | 0.36 | 0.20 | 0.17 | 0.26 | 1.21 |
| All cyclists, 2014–2020 | 596 | 1.57 | 0.32 | 0.25 | 0.20 | 0.25 | 1.35 |
| All cyclists, 2014–2022 | 710 | 1.50 | 0.34 | 0.24 | 0.19 | 0.24 | 1.41 |
| Children, 2014–2018 | 174 | 1.46 | 0.34 | 0.10 | 0.09 | 0.26 | 1.58 |
| Children, 2014–2020 | 221 | 1.56 | 0.32 | 0.17 | 0.14 | 0.25 | 1.55 |
| Children, 2014–2022 | 261 | 1.53 | 0.32 | 0.16 | 0.14 | 0.24 | 1.56 |

So a corner's own bike count gets about a fifth of the weight in the
all-cyclist rankings here and a seventh or less in the child rankings, and
the fitted background the rest.

The values are stable between fits. The street bike power is above 1
because the strong pull narrows the range of the street averages and the
power widens it again; it is not an estimate of how crashes grow with bike
traffic. The car power, about a third, is not the $a$ of a traffic model
either: the two powers describe how the two crash records predict bike
crashes together (appendix A.6).

## 12. Why each choice was made

Each choice was made by comparing fits on the fitting years, then checked on
the later years. The later years were seen during development (section
4.1), so they confirm rather than test.

### 12.1 Poisson counts with gamma-distributed rates

If rates did not vary between corners with the same surroundings (a plain
Poisson, $s \to \infty$), a corner's own count would add nothing to the
expectation. They do vary: the counts are overdispersed against any
expectation tried. The gamma is the conjugate choice, which gives the
closed-form blend of section 11.6 and the negative binomial likelihood.
This is the standard model for crash counts (Hauer 1997; Highway Safety
Manual).

### 12.2 The spread power, fixed at 1

How much the corner's own count should weigh depends on how the spread of
rates grows with the expectation (appendix A.3):

- With $p = 1$, every corner's own count gets the same weight,
  $\alpha/(1 + \alpha)$, whatever its expectation.
- With $p = 2$, the textbook negative binomial, the weight is
  $\alpha\mu/(1 + \alpha\mu)$: it rises with the expectation, and a corner
  where little is expected is held close to it.
- In between, the weight still rises with the expectation, more slowly. What
  grows as the expectation falls is the proportional effect of a first
  crash, $1 + \alpha\mu^{p-2}$, not the weight.

The model first fitted $p$. On the Los Altos study area it came out between
1.2 and 1.6, and across 62 windows in 23 cities between 0.51 and 2.49, above
2 in two of them. Above 2 the estimate at a corner with no crash can fall as
its expectation rises (where $\alpha(p - 2)\mu^{p-1} > 1$).

Fitting it did not improve the rankings. Refitting every window with
$p = 1$ and with $p$ fitted (`python -m bike_safety_ca.checks.candidates`,
revision `88d0e04`, crash tables of 21 November 2026), the average change
from fitting $p$ to fixing it at 1 is, with shares in percentage points of
the later crashes:

| Ranking | Windows (cities) | Rank score | Top 25 | Top 50 | Top 100 | Top 5% of corners |
|---|---|---|---|---|---|---|
| Fitted to all cyclists, scored on all cyclists | 62 (23) | −0.0002 | −0.18 | +0.13 | −0.17 | +0.08 |
| Fitted to all cyclists, scored on children | 33 (17) | −0.0004 | −0.16 | +0.08 | −0.23 | +0.27 |
| Fitted to children, scored on children | 18 (7) | +0.0003 | −0.25 | −0.15 | +0.14 | −0.33 |

The margins written down before the comparison were 0.005 of rank score and
1 percentage point in the top 50 and the top 5% of corners. Drawing whole
cities again with replacement 10,000 times, the all-cyclist rank-score
change stays between −0.0007 and +0.0003 (5th to 95th percentile), and the
top-25 change between −0.58 and +0.22 points. So the rankings use $p = 1$:
one parameter fewer, no search over $p$, and a weight that can be stated in
a sentence. These are the windows the model was developed on, and windows
within a city overlap, so this shows average differences inside the margins
here, not that the two are equivalent.
`rank_intersections(..., spread_power=None)` still fits $p$. The corridor
table (`model/corridors.py`) keeps the fitted power for its corner part; it
has not been compared.

What fixing the power costs:

- **The very top of the list.** The top 25 and the top 100 had no margin of
  their own, and both come out a little lower on average: over the 62
  all-cyclist windows the top 25 lists hold 1,787 later crashes with $p = 1$
  and 1,810 with $p$ fitted. In three more cities than before (five in all),
  past bike crashes alone now match or beat the model's top 25 (see the
  companion note).
- **Single windows move more than the averages.** In the Los Altos study
  area the ranking fitted to child crashes through 2018 finds 4 of 87 later
  child crashes in its top 25 with $p = 1$ and 10 with $p$ fitted, with the
  same 14 in its top 50.
- **The likelihood is lower in the largest cities.** Over the 64
  all-cyclist windows with a fitted model, the AIC is lower with $p = 1$ in
  32, higher by more than 2 in 28 and higher by more than 10 in nine: all
  three windows of San Francisco (by 56 to 90, where the fitted power is
  about 1.6) and of Long Beach, two of San Diego and one of Ventura. The
  simulation of section 5.4 shows the same thing: with $p = 1$ San
  Francisco's real score is below nearly every one of its simulated scores.
  (One-off script calling `fit_street_model`, revision `0b56c05`.)

An earlier version of this section concluded from the AIC that the
estimates at the busiest corners are less trustworthy with $p = 1$. A direct
check does not bear that out. Forecasting each closed later period from the
fitting years and comparing with what was recorded (40 windows in 21
cities, section 12.11), the corners in the model's own top 25 were forecast
at 1.35 times the crashes later recorded with $p = 1$, and at 1.45 times
with $p$ fitted between 1 and 2. Both are too high, and $p = 1$ is the
less wrong of the two there. Over all corners the two differ by 0.0008 in
Poisson deviance per intersection, in favour of the fitted power.

A power fitted but held between 1 and 2 was compared as well, since it keeps
the estimate monotone. Against it, $p = 1$ changes the all-cyclist rank
score by −0.0004 (−0.0008 to 0.0000) and the top 25 by −0.20 points, the
top 50 by +0.13 and the top 5% by +0.05. That is inside the margins, so the
simpler setting was kept.

### 12.3 Crash records in place of traffic

No city in the tests has counts of bike traffic at its intersections, and
car counts cover few streets. Under assumption 3, car flow can be replaced
by the car-crash rate, $V^{a} \propto (\lambda^{\text{car}})^{a/q}$, and the
bike flow along a street by the street's bike-crash record. The earlier
one-off checks support the substitution: on the 70 study-area streets with
measured daily car volumes and three or more intersections, measured volume
had a rank correlation of 0.72 with car crashes per corner and 0.59 with
bike crashes per corner (not rerun).

### 12.4 Leaving the corner out of its street average, and pulling hard

**Leaving it out.** Bike crashes are what the model fits. If a corner's own
bike count were in its street average, the same number would be on both
sides of the fit and the street term would take credit for the corner's
own record. So blend A uses the other corners only, and the corner's own
count enters only in blend C. Two indirect routes remain: $t(n)$ is fitted
on all streets, and each corner's count is in its neighbours' averages.
Car crashes are only a predictor, so the corner's own car count goes
straight into blend B.

**Toward a length-typical value.** The median named street has two
intersections, so most street averages rest on very little. Pulling a
short street with no record toward the overall mean, as the first version
of the model did, rates it too high: bike crashes per corner rise with
street length, roughly as $n^{0.7}$ (children $n^{0.6}$, car crashes
$n^{0.84}$; earlier one-off fits, not rerun).

**Pulling hard.** Training log-likelihood on the study area, all cyclists
(rerun, same script as section 11.9):

| Fitted on | $Q = 1$ | $Q = 8$ | $Q = 20$ | $Q = 40$ |
|---|---|---|---|---|
| 2014–2018 | −1064 | −1044 | −1038 | −1041 |
| 2014–2020 | −1286 | −1257 | −1250 | −1256 |
| 2014–2022 | −1439 | −1411 | −1404 | −1411 |

The fit improves up to about 20 imaginary corners in every window and falls
off after. With $Q = 20$, a street's own record counts for much only on
long streets.

**The car pull.** For car crashes the strength hardly matters: going from 1
to 3 or 8 imaginary corners changed the training log-likelihood by about 1
in the earlier one-off runs, so it is left at 1. With a car shape of about
0.25, the corner's own car count gets more than half the weight wherever
the street average is above 0.25 crashes; the street average mainly decides
what a corner with no car crash gets in place of zero.

**Why only blend C has a spread power to choose.** In C the power decides
how much one bike crash moves a corner with a low expectation, and the
training log-likelihood is lower by 2 to 4 with $p = 2$ than with $p = 1$
in each window. In B the textbook form is used with one fitted shape. Another
power for the car blend has not been tried; given how little the car pull
matters, it is unlikely to change much.

### 12.5 Adding the averages of a corner's streets

Riders arrive along both streets, so the bike flow through a corner is the
sum of the flows on its streets, not their mean (appendix A.7). The sum fit
the fitting years better than the mean in the earlier one-off runs (AIC
lower by about 30 to 50; not rerun).

### 12.6 What each choice contributes

One-off runs on the study area, all cyclists, from when the model fitted
$p$; not rerun since the fixes of 15 to 21 November 2026, which moved the
model's study-area score by 0.002 at most, or since $p$ was fixed at 1,
which moved it by 0.001. Average rank score over the three windows (section 4), and the forecast
log-likelihood summed over the windows with the level set to the actual
total (higher is better):

| Version | Study area | Los Altos | Log-likelihood, study area |
|---|---|---|---|
| First version: mean over streets, pulled to the overall mean, $p = 2$ | 0.817 | 0.796 | −1880 |
| Sum over streets | 0.824 | 0.792 | −1861 |
| and $p$ fitted | 0.827 | 0.810 | −1845 |
| and pulled to the street-length value, $Q = 20$ (the model before $p$ was fixed) | 0.856 | 0.847 | −1792 |
| Street length alone, no street bike record | 0.849 | 0.842 | −1825 |
| Crash history with same-street averages (earlier fitted formula) | 0.836 | 0.828 | −1850 |

The pull toward the length-typical value is the largest single gain. Street
length alone does most of the work of the street term; the street's own
bike record adds a little, mainly on long streets.

### 12.7 Road and traffic information that was tried

Three kinds of extra information were tried on top of the model in earlier
one-off runs on the study area (not rerun; scripts not included). Average
rank score over the three windows:

| Version | Study area, all | Study area, children | Los Altos, all | Los Altos, children |
|---|---|---|---|---|
| The model | 0.856 | 0.853 | 0.847 | 0.847 |
| Pulled toward the typical value for road class, not length | 0.842 | 0.834 | 0.815 | 0.806 |
| Pulled toward the typical value for class and length | 0.852 | 0.847 | 0.833 | 0.828 |
| Plus major and minor road class as corner factors | 0.860 | 0.857 | 0.846 | 0.848 |
| Measured car volume in the value a street is pulled toward | 0.850 | | 0.841 | |
| Plus modelled school bike trips through the corner | 0.857 | 0.866 | 0.851 | 0.852 |
| Road-and-traffic model of the Los Altos analysis, refitted | 0.856 | 0.866 | 0.830 | 0.808 |

- **Road class** is a worse target than length. Once the corner's car record
  is in the model, car crashes already carry what class knows; length adds
  something else, whether the street is a through route. Class as corner
  factors improves the training fit a little; the gain on later crashes is
  within noise.
- **Measured car volumes** cover 70 streets touching 1,183 of the 4,208
  intersections. As a separate corner factor they move the rank score by
  0.003 or less, with a fitted power of about −0.3: given the same crash
  record, a corner on a busier street has slightly fewer bike crashes.
- **Modelled school bike trips**, $(1 + \text{trips})^{g}$ with $g \approx
  0.35$, close the gap to the road-and-traffic model for children across the
  study area (resampling range +0.003 to +0.024), but not clearly in Los
  Altos. The term is not in `fit_street_model`; the trips come from a route
  model that is not in this repository.

### 12.8 Tried and dropped

All on the fitting years first, in earlier one-off runs:

- **Older crashes counting for less.** An old crash predicts later ones
  about as well as a recent one; no consistent difference across windows.
- **The street's car record as an extra factor.** Fitted power near zero.
- **Street bike crashes per car crash, not per corner.** Fits much worse.
- **Pulling street averages toward a value predicted from the street's car
  record.** No gain.
- **Street length as a separate factor beside the street average.** No
  better than the pull, with one more parameter.
- **Dividing the corner's car count by its street's car average**, which
  the theory suggests if bike flow were constant along a street. Worse.
- **No-fit versions of the product with a fixed shape.** They rank about as
  well as the hand-built blend (0.82 to 0.83) but are far too concentrated
  to be read as expected counts.

### 12.9 How the earlier formulas relate to it

Two earlier rankings are still in the code and in the hold-out table. The
model explains why they worked.

The hand-built blend, `street_blend_score` (also the fallback, section 6),
is a product of the corner's bike and car counts, each first blended with
its street mean (appendix A.9). The product is assumption 3; the
fixed-weight blend of a corner with its street is blend C with $p = 1$; the
"1 +" keeps a corner with no record from scoring zero, the job the pull does
in blend A.

The earlier fitted formula, `fit_history_model`, is a negative binomial fit
on $(1 + x_i)$, $(1 + \text{street bike sum})$ and
$(1 + \text{street car sum})$, where "street sum" is the sum over a corner's
streets of the mean at the street's other corners, with no pull. Its fitted
powers were about 0.8, 1.9 and 0.5 to 1.0. Raw street sums with "1 +" never
lift a street with no record to the average, so short streets are treated
as quiet; the power of 1.9 trusts a street's record mainly where it is
large, which imitates the strong pull; and the "1 +" floors compress the low
end, as $p < 2$ does.

### 12.10 How this relates to published methods

Parts of the model are standard, parts are close to published methods
without being the same, and parts are this project's own.

**The same mathematics.**

- Blend C, a model's expectation combined with the site's own count through
  a gamma–Poisson posterior, is the empirical Bayes estimate of road safety
  (Hauer 1997; Hauer and others 2002 is the short tutorial). The Highway
  Safety Manual uses the case $p = 2$, where the weight on the model's
  expectation is $1/(1 + \alpha\mu)$. With $p = 1$ it is $1/(1 + \alpha)$
  at every site.
- The variance $\mu + \alpha\mu^{p}$ is the NB-P family of Greene (2008),
  with the two usual negative binomial models, NB1 and NB2, as $p = 1$ and
  $p = 2$.
- Blend A's weight on a street's own record, $(n - 1)/(n - 1 + Q)$, is a
  Bühlmann credibility factor (Bühlmann 1967; appendix A.5).

**Close, but not the same.**

- Wang, Zhao and Jackson (2019) compare NB1, NB2 and NB-P for crashes at
  rural two-lane intersections, and El-Basyouny and Sayed (2006) compare a
  fixed with a site-varying negative binomial shape on road segments. The
  question of section 12.2, whether a more flexible spread changes what the
  model is used for, is theirs; the finding here, a better fit to the counts
  in some cities with nearly the same order, is for this project's data
  only.
- Katicha and Flintsch (2023) combine a spatially smoothed crash estimate
  with each location's own count by empirical Bayes (their KDEB). The street
  averages here play the part of their smoothed estimate, but they are
  averages along named streets and not a kernel over distance, they leave
  the corner out, they are pulled toward a value typical of the street's
  length, and a car-crash term stands beside them. KDEB has not been run on
  these data, so nothing here says which does better.

**This project's own, and not compared with a published method:** street
averages that leave the corner out and are pulled toward a length-typical
value; car crashes standing in for car traffic; adding the averages of a
corner's streets. Their support is the hold-out comparisons of this
section and no more.

### 12.11 Textbook models fitted to the same data

The model's steps were arrived at by trial on the test windows, so it was
compared with three models that a statistician would write down first. All
use the same crashes, the same placement, the same 100-crash floor and the
same tests (`python -m bike_safety_ca.checks.candidates`, revision
`88d0e04`, crash tables of 21 November 2026).

- **Textbook empirical Bayes** (`model/standard_eb.py`). A negative binomial
  regression (NB2, fitted with statsmodels) of the bike count on the corner's
  car crashes and the classes of its two main roads, then the usual update
  with the corner's own count (Hauer and others 2002). No predictor is built
  from bike crashes.
- **The same with street context.** Two more regression columns, set before
  the run by an outside reviewer and not varied: the number of other
  intersections sharing a named street with the corner, and the car crashes
  per year at those intersections.
- **Street effects fitted jointly** (`model/street_effects.py`). The textbook
  model with a normally distributed effect for each named street, fitted in
  one step by an approximate method written for this comparison. It has not
  been checked against a maintained package and stays experimental.

The margins were written down beforehand: a mean loss of no more than 0.005
of rank score, and 1 percentage point of later crashes in the top 50 and in
the top 5% of corners, against the model with the power fitted between 1 and
2. Change from that reference, rankings fitted to and scored on all
cyclists, 62 windows in 23 cities (5th to 95th percentile over 10,000 draws
of whole cities in brackets):

| Model | Rank score | Top 25 | Top 50 | Top 5% of corners |
|---|---|---|---|---|
| This model, $p = 1$ | −0.0004 (−0.0008 to 0.0000) | −0.20 | +0.13 | +0.05 |
| Textbook empirical Bayes | −0.0235 (−0.0275 to −0.0200) | −1.06 | −0.57 | −1.59 |
| With street context | −0.0077 (−0.0099 to −0.0055) | −0.68 | −0.16 | −0.88 |
| Street effects fitted jointly | −0.0102 (−0.0124 to −0.0081) | −0.29 | −0.29 | −0.59 |

None of the three meets the rank-score margin, so the model was kept.
Measured against $p = 1$ itself the street-context model loses 0.0073
(0.0049 to 0.0095), and on the 40 windows whose later period ends in 2022,
before any provisional records, 0.0073: the conclusion does not depend on
the reference or on the newest records.

What this does and does not show:

- The two street-context columns recovered about two thirds of the textbook
  model's rank-score gap on these windows. Much of what this model adds is
  information about the corner's streets, which a textbook model can use
  too. The comparison does not separate the rest into better inputs and
  better machinery.
- The street-context model is the closest conventional comparator: a
  standard likelihood, standard software and no predictor built from bike
  crashes. It loses 0.2 points of later crashes in the top 50 and 0.9 in
  the top 5%, which is inside those margins, and 0.7 points in the top 25.
  It is kept in the comparison command as the standing benchmark for later
  changes.
- For rankings fitted to child crashes (18 windows in 7 cities) it loses
  0.0073 of rank score (0.0002 to 0.0147) and 1.5 points in the top 50
  (from 4.2 lost to 0.5 gained).
- Forecast counts were checked on the 40 closed later periods (2019–2022 or
  2021–2022; whether every agency's records are complete for those years
  was not audited). Every model forecast the same total to within 0.03% in
  every window, and over all of them the crashes recorded were 79% of that
  total. The windows overlap, and this is a mismatch between these periods,
  not a measured trend. In each model's own top 25 corners the forecast was
  1.35 times what was recorded for this model with $p = 1$, 1.45 with the
  power fitted, and 1.61 to 1.68 for the three textbook models. Poisson
  deviance per intersection, which with equal totals mainly measures where
  each model puts the crashes, is higher than the reference's by 0.0008 for
  $p = 1$, 0.0062 for street effects, 0.0074 for street context and 0.0161
  for the plain textbook model.
- All of this is on the windows the model was developed on. The
  street-context model was later scored on cities held back from
  development, where it is 0.6 points of capture behind this model, and the
  plain textbook model, 0.9 behind (section 1.2). The street-effects model
  was not.

The decision record, with the full tables, is
[plans/model-review-decision.md](../plans/model-review-decision.md). Its
figures are those of 23 November 2026, when the decision was made, before
crashes at the edge of an area were counted (section 7.5); the figures
above are the rerun.

## Appendix: derivations

Notation as in section 11.1. Gamma distributions are written with shape and
rate, $\text{Gamma}(s, \beta)$, with mean $s/\beta$ and variance $s/\beta^2$.

### A.1 The negative binomial

Let $y \mid \lambda \sim \text{Poisson}(\lambda)$ and
$\lambda \sim \text{Gamma}(s, s/\mu)$, so $E[\lambda] = \mu$ and
$\text{Var}[\lambda] = \mu^2/s$. Integrating out $\lambda$,

$$
P(y) = \frac{\Gamma(s + y)}{\Gamma(s)\, y!}
\left(\frac{s}{s + \mu}\right)^{s}
\left(\frac{\mu}{s + \mu}\right)^{y},
$$

with $E[y] = \mu$ and $\text{Var}[y] = \mu + \mu^2/s$. Setting
$s = \mu^{2-p}/\alpha$ gives $\text{Var}[y] = \mu + \alpha\mu^{p}$: $p = 2$ is
the usual negative binomial with constant shape $1/\alpha$, and $p = 1$ has
variance $(1 + \alpha)\mu$. The log-likelihood maximised in section 11.5 is the
sum of $\log P(y_i)$ with $\mu_i$ and $s_i$ in place of $\mu$ and $s$.

### A.2 The posterior mean

The posterior is proportional to
$\lambda^{y} e^{-\lambda} \cdot \lambda^{s-1} e^{-s\lambda/\mu}$, so

$$
\lambda \mid y \sim \text{Gamma}\bigl(s + y,\; s/\mu + 1\bigr),
\qquad
E[\lambda \mid y] = \frac{s + y}{s/\mu + 1} = \frac{\mu(s + y)}{s + \mu}
= w\mu + (1 - w)\,y,
$$

with $w = s/(s + \mu)$. This is the estimate ranked by (section 11.6).

### A.3 The spread power and the weight on a corner's own count

With $s = \mu^{2-p}/\alpha$, the weight on the corner's own count is

$$
1 - w = \frac{\mu}{s + \mu} = \frac{\alpha\mu^{p-1}}{1 + \alpha\mu^{p-1}}.
$$

- $p = 1$ (the rankings): $1 - w = \alpha/(1 + \alpha)$ for every corner.
- $p = 2$: $1 - w = \alpha\mu/(1 + \alpha\mu)$, which goes to zero as $\mu$
  falls: a corner with a low expectation is held at it.
- $1 < p < 2$: in between. The weight is smaller at a corner with a lower
  expectation, but less so than at $p = 2$.

The effect of one crash is the ratio of the estimates at $y = 1$ and
$y = 0$:

$$
\frac{E[\lambda \mid y = 1]}{E[\lambda \mid y = 0]} = \frac{s + 1}{s}
= 1 + \alpha\mu^{p-2}.
$$

At $p = 2$ this is $1 + \alpha$ everywhere. At $p < 2$ it grows as $\mu$
falls, so one crash at a corner where little was expected moves the
estimate a long way; at $p = 1$ the ratio is $1 + \alpha/\mu$. When $p$ is
fitted (`spread_power=None`), it is chosen by maximising the profile
log-likelihood $\ell(p) = \max_{\gamma_0, a, b, \alpha} \sum_i \log P(y_i)$,
and the AIC counts it as a parameter.

### A.4 The forecast

Let $z$ be the count in a later period $r$ times as long, with
$z \mid \lambda \sim \text{Poisson}(r\lambda)$, and write
$S = s + y$, $R = s/\mu + 1$ for the posterior of A.2. Then

$$
E[z] = \frac{rS}{R}, \qquad
\text{Var}[z] = E[r\lambda] + \text{Var}[r\lambda]
= \frac{rS}{R} + \frac{r^2 S}{R^2},
$$

$$
P(z = 0) = \left(\frac{R}{R + r}\right)^{S}, \qquad
P(z = 1) = S\,\frac{r}{R + r}\left(\frac{R}{R + r}\right)^{S}.
$$

Section 4.5 sums $1 - P(z = 0)$ over intersections for the expected number
with at least one later crash, and $1 - P(z = 0) - P(z = 1)$ for two or
more. These treat $\mu_i$ and $s_i$ as known.

### A.5 The street average as a credibility estimate

Suppose the corners of street $r$ share a per-corner rate $\theta_r$, with
$\theta_r \sim \text{Gamma}(Q\,t(n_r), Q)$ (mean $t(n_r)$, variance
$t(n_r)/Q$), and each corner's count is Poisson with mean $\theta_r$. Given
the other $n_r - 1$ corners, whose counts total $Y_r - y_i$, A.2 gives

$$
E[\theta_r \mid \text{others}] = \frac{Q\,t(n_r) + (Y_r - y_i)}{Q + n_r - 1}
= Z\,\frac{Y_r - y_i}{n_r - 1} + (1 - Z)\,t(n_r),
\qquad Z = \frac{n_r - 1}{n_r - 1 + Q},
$$

which is the formula of section 11.3. The second form needs $n_r > 1$; a
street with one intersection has $Z = 0$ and uses $t(1)$ directly, as the
first form and the code do. $Z$ is Bühlmann's credibility factor
(Bühlmann 1967), with $Q$ the ratio of the variance within a street to the
variance between streets. With $Q = 20$ a street's own record has half the
weight only at 21 intersections. In the data corners on one street vary
more than Poisson, so $Q$ is chosen by fit (section 12.4) rather than taken
from this derivation. One $Q$ for all lengths implies that the variance of
$\theta_r$ is proportional to $t(n_r)$.

### A.6 Car crashes in place of car traffic

Under assumption 3, $\lambda^{\text{car}} = c'V^{q}$, so
$V = (\lambda^{\text{car}}/c')^{1/q}$ and

$$
\lambda^{\text{bike}} = c\,V^{a}B^{b}
= c''\,(\lambda^{\text{car}})^{a/q}\,B^{b}.
$$

This is the reason for the form of the model, not a reading of its fitted
powers. $\tilde x_i$ estimates $\lambda^{\text{car}}_i$, so with $B$ known
the power on it would estimate $a/q$, not $a$. But $B$ is not known: the
street bike term stands in for it through the bike crashes of the street,
which themselves depend on car traffic, street design and reporting. The two
terms share that information, so neither fitted power is $a/q$ or $b$, and
neither says what a change in traffic would do. If the street term alone
predicted bike crashes perfectly, the car power would be fitted as zero
whatever the effect of car traffic.

### A.7 Adding the streets' averages

Riders reach a corner along each of its streets, so the bike flow through
it is close to $B_i \approx \sum_{r \in R(i)} B_r$ (riders who turn are
counted once on each street, which this ignores). If the street averages
are proportional to the streets' bike flows, their sum is proportional to
$B_i$ and their mean to $B_i/|R(i)|$. In the log-linear model,

$$
b\log\Bigl(\frac{1}{|R(i)|}\sum_r \bar m_r\Bigr)
= b\log\sum_r \bar m_r - b\log|R(i)|,
$$

so the choice between sum and mean comes down to whether a corner on more
named streets gets more: the sum gives a corner on $k$ streets $k^{b}$ times
what the mean gives. For corners on one named street they agree.

### A.8 The typical value for a street length

The Poisson regression of section 11.2 has score equations

$$
\sum_r \bigl(Y_r - n_r t(n_r)\bigr) = 0, \qquad
\sum_r \log n_r\,\bigl(Y_r - n_r t(n_r)\bigr) = 0.
$$

The first says that the typical values, summed over every corner of every
street, add up to the crashes on all streets; the second that they do so
for long and short streets alike, on the log scale. A corner on two streets
is counted on both. The offset makes $t(n)$ a rate per corner.

### A.9 The hand-built blend

`street_blend_score` uses, for counts $v$ (bike or car) and weight $\omega$,

$$
\text{shrink}_i(v, \omega) = \frac{v_i + \omega\,\bar v_i}{1 + \omega},
\qquad \bar v_i = \frac{1}{|R(i)|}\sum_{r \in R(i)} \frac{V_r}{n_r},
$$

where $V_r$ is the street total including corner $i$; a corner on no named
street keeps $\bar v_i = v_i$. The score is

$$
\bigl(1 + \text{shrink}_i(y, 1)\bigr)\,\bigl(1 + \text{shrink}_i(x, 0.5)\bigr).
$$

The product is assumption 3 with both powers 1. Each shrink gives the
corner's own count a fixed weight, $1/(1 + \omega)$, as blend C does with
$p = 1$ (A.3). The "1 +" keeps a corner with no record from scoring zero.
Being a product of shrunk counts, it orders intersections but is not an
expected count.

### A.10 The rank score and its standard error

With $n_1$ intersections that had a later crash and $n_0$ that did not, and
$\rho_j$ the mid-rank of intersection $j$'s score among all of them,

$$
A = \frac{\sum_{j:\,\text{hit}} \rho_j - n_1(n_1 + 1)/2}{n_1 n_0}
= P(S_{\text{hit}} > S_{\text{miss}}) + \tfrac{1}{2}P(S_{\text{hit}} = S_{\text{miss}}),
$$

the Mann–Whitney statistic scaled to $[0, 1]$ (`rank_score`). An
intersection with two later crashes counts once. Hanley and McNeil (1982)
give the standard error under exponential score distributions:

$$
\text{SE}(A)^2 = \frac{A(1 - A) + (n_1 - 1)(Q_1 - A^2) + (n_0 - 1)(Q_2 - A^2)}{n_1 n_0},
\qquad Q_1 = \frac{A}{2 - A}, \quad Q_2 = \frac{2A^2}{1 + A}.
$$

When $n_0$ is in the thousands the last term dominates and
$\text{SE}(A)^2 \approx (Q_2 - A^2)/n_1$. At $A = 0.8$, $Q_2 - A^2 = 0.071$,
so the standard error is about 0.084 at $n_1 = 10$ and 0.049 at
$n_1 = 30$. Here $n_1$ counts intersections; the floor of 30 in the
hold-out counts crashes, so a scored window can have $n_1$ below 30. The
formula treats intersections as independent and ignores ties, which are
many among quiet corners.

### A.11 Crashes at the top $k$ with ties

Let $c$ be the $k$-th highest score, $U$ the intersections scoring above
$c$ and $T$ those scoring exactly $c$. `top_share` returns

$$
\sum_{j \in U} z_j + \frac{k - |U|}{|T|}\sum_{j \in T} z_j,
$$

the expected count at the top $k$ when ties at the cut are broken at random.

### A.12 The reporting check's rules

**Yearly flags** (`tims.agency_reporting_gaps`). For agency $g$ with yearly
counts $n_{gj}$:

1. Typical year $T_g$: the median of the finished years; then the median of
   the years within $[0.6\,T_g,\; T_g/0.6]$, repeated until the set of years
   stops changing (all years are used if fewer than three are left).
2. Expected count $E_{gj} = T_g f_j$, with $f_j = 1$ except in an unfinished
   last year, where it is the share of the year up to the last crash date
   (a year is unfinished when that share is under 0.95).
3. Own ratio $\rho_{gj} = n_{gj}/E_{gj}$. Region ratio $\tilde\rho_j$: the
   median of $\rho$ over the other agencies with $T \ge$ the minimum
   baseline. Relative ratio $\rho_{gj}/c_j$, with
   $c_j = \min(\max(\tilde\rho_j, 0.6), 1/0.6)$, or 1 where there are no
   other agencies to compare with.
4. A fall is marked when both ratios are under 0.4; a possible fall when
   both are under 0.6 and not both under 0.4. Rises mirror this at 2.5 and
   1/0.6, and are never marked in an unfinished year.
5. Every mark needs $T_g$ of at least 20 (8 for cyclist crashes) and a
   Poisson tail beyond the count, $P(N \le n_{gj})$ for a fall or
   $P(N \ge n_{gj})$ for a rise with $N \sim \text{Poisson}(E_{gj})$, under
   0.001.

Because the region ratio is held within $[0.6, 1/0.6]$, the other agencies
can excuse a move of up to that size that they share, never a collapse, and
a move of theirs can never cause a mark.

**Lasting changes of level** (`reporting.level_step`), over the finished
years of each agency and measure:

1. Split the years at every point that leaves three or more on each side.
   Take the median of each side; call them low and high.
2. The split counts if high is at least 20 and low is under 0.6 times high,
   and at most one year lies on the wrong side of the midpoint
   $\sqrt{\text{low}\cdot\text{high}}$ (or high/2 when low is 0), and that
   year is not one of the two next to the split.
3. Of the splits that count, the one with fewest years out of place wins,
   then the largest change in $\log((\text{high} + 1)/(\text{low} + 1))$.
4. For a step at one severity, "moved" is the share of the change that the
   agency's other severities took up in the opposite direction. It is
   "regraded" when that share is between 0.5 and 2 and the severity is a
   fifth or more of the agency's injury crashes; otherwise "fewer reports"
   or "more reports".

At most one step per agency and measure is reported.

## References

Checked on 16 November 2026. The four papers were checked against the
publisher's or an archive's record, and Greene's variance form against the
paper itself. The two books were checked for their details and subject only:
the text of neither was read for this note. Hanley and McNeil, added on 22
November 2026, was checked against its Crossref record that day. The four
papers of section 12.10 marked "details only", added on 23 November 2026,
were checked against their Crossref records for authors, title, journal and
pages; their text was not read for this note, and what section 12.10 says of
them follows an outside literature review of their abstracts.

- Hauer, E. (1997). *Observational Before–After Studies in Road Safety:
  Estimating the Effect of Highway and Traffic Engineering Measures on Road
  Safety*. Pergamon, Oxford. xv + 289 pp. ISBN 0-08-043053-8. Regression to
  the mean and the empirical Bayes method (section 11.6).
- Hauer, E., Harwood, D. W., Council, F. M. and Griffith, M. S. (2002).
  "Estimating safety by the empirical Bayes method: a tutorial."
  *Transportation Research Record* 1784(1), 126–131. doi:10.3141/1784-16.
  Details only.
- Katicha, S. W. and Flintsch, G. W. (2023). "A kernel density empirical
  Bayes (KDEB) approach to estimate accident risk." *Accident Analysis &
  Prevention* 186, 107039. doi:10.1016/j.aap.2023.107039. Details only.
- Wang, K., Zhao, S. and Jackson, E. (2019). "Functional forms of the
  negative binomial models in safety performance functions for rural
  two-lane intersections." *Accident Analysis & Prevention* 124, 193–201.
  doi:10.1016/j.aap.2019.01.015. Details only.
- El-Basyouny, K. and Sayed, T. (2006). "Comparison of two negative binomial
  regression techniques in developing accident prediction models."
  *Transportation Research Record* 1950(1), 9–16.
  doi:10.1177/0361198106195000102. Details only.
- AASHTO (2010). *Highway Safety Manual*, 1st edition. American Association
  of State Highway and Transportation Officials, Washington, DC. Three
  volumes. ISBN 978-1-56051-477-0. Part C gives intersection crash models as
  products of powers of the traffic on the two roads, and the empirical Bayes
  weighting of a model's prediction with a site's own count.
- Greene, W. (2008). "Functional forms for the negative binomial model for
  count data." *Economics Letters* 99(3), 585–590.
  doi:10.1016/j.econlet.2007.10.015. The variance form $\mu + \alpha\mu^{p}$
  (his equation 2-15, with $\alpha = 1/\theta$), which has the usual two
  forms as the cases $p = 1$ and $p = 2$.
- Bühlmann, H. (1967). "Experience rating and credibility." *ASTIN Bulletin*
  4(3), 199–207. doi:10.1017/S0515036100008989. The weight given to a unit's
  own record (appendix A.5).
- Jacobsen, P. L. (2003). "Safety in numbers: more walkers and bicyclists,
  safer walking and bicycling." *Injury Prevention* 9(3), 205–209.
  doi:10.1136/ip.9.3.205. The journal's page notes a later correction.
- Elvik, R. and Bjørnskau, T. (2017). "Safety-in-numbers: a systematic
  review and meta-analysis of evidence." *Safety Science* 92, 274–282.
  doi:10.1016/j.ssci.2015.07.017. Pooled powers of about 0.5 for motor
  traffic, 0.43 for cyclists and 0.51 for pedestrians.
- Hanley, J. A. and McNeil, B. J. (1982). "The meaning and use of the area
  under a receiver operating characteristic (ROC) curve." *Radiology*
  143(1), 29–36. doi:10.1148/radiology.143.1.7063747. The standard error of
  the rank score (appendix A.10).

## Data credits

Crash figures here are built from two sources:

- Transportation Injury Mapping System (TIMS), Safe Transportation Research
  and Education Center, University of California, Berkeley.
- California Crash Reporting System (CCRS), California Highway Patrol, via
  data.ca.gov.

Street data © OpenStreetMap contributors, ODbL 1.0. See "Crash
records" in `docs/guide.md` for each source's terms.
