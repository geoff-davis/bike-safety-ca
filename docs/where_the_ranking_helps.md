# Where the ranking helps most and least

The ranking was run on 28 California cities and four pooled areas in November
2026 to see where it works, where it does not, and what can be done about it.
This note gives the results, what they suggest, and the limits found along the
way, each with its workaround where there is one.

These are retrospective tests, one run per city, on years the model's design
had already seen for Los Altos. Read the differences between cities as a guide
to where to be careful, not as measured accuracy.

## What was run

Each city has a config in `config/`, with the Los Altos case study's windows and child age: fit
through 2018 and test 2019–2022; fit through 2020 and test 2021–2022; fit
through 2022 and test 2023 on; children are 18 or under. Unlike the case
study, which starts in 2014, these start in 2015, because TIMS no longer
offers 2014. Crash records are TIMS exports for 2015 to June 2026 merged with
CCRS. Throughout, a "crash" is a police-recorded injury crash that could be
placed at an intersection, and child figures cover cyclists of known age only. Streets are from OpenStreetMap and city limits from the Census Bureau.
Each city is built with the commands in the guide's "The area and its
streets" and "Building the crash tables", into `data/processed/<config name>/`. The cross-city tables
in this note (the results, pooling, ranking children, lasting changes of
level, and with and without minor crashes) are then printed by

```bash
uv run python -m bike_safety_ca.checks.cities --configs config --pool 'pool_*' --out output/cities
```

which also writes the rows behind them. It prints every pooled area a city
is in; the pooling table here shows one for each city. The simulation under
"What the rank score does and does not tell you", the comparison of the two
reporting rules and the figures on single streets and agencies were separate
analyses and are not part of the command.

The **rank score** is the area under the ROC curve: the chance that an
intersection with a later bike crash is ranked above one without (0.5 is a
coin toss, 1.0 perfect). See "What the rank score does and does not tell you"
below before comparing cities on it.

## Results

All cyclists unless marked. Mean over the windows scored: a window with
fewer than 30 later crashes is left unscored, since a score on a handful of
crashes is close to those crashes' own ranks. "Past bike crashes" is
the ranking by past bike crashes only, under the name the hold-out command
prints; the text below calls it history alone. "Fit" says whether the street-length
model was fitted in every window, in some ("mixed"), or the hand-built blend
was used throughout for want of crashes. "Top 100" is later bike crashes at
the 100 highest-ranked intersections, summed over the windows scored (which
overlap, so use it only to compare the two rankings).

| City | Intersections | Windows scored | Rank score | Past bike crashes | Fit | Top 100: model / history, of all later crashes | Rank score, 18 or under (windows scored) | Fewest later child crashes in a window |
|---|---|---|---|---|---|---|---|---|
| Irvine | 4,983 | 3 | 0.904 | 0.679 | model | 167 / 131 of 491 | 0.895 (3) | 54 |
| Huntington Beach | 3,571 | 3 | 0.895 | 0.682 | model | 356 / 286 of 893 | 0.880 (3) | 53 |
| San Jose | 14,136 | 3 | 0.893 | 0.678 | model | 333 / 242 of 1,828 | 0.835 (3) | 79 |
| Sacramento | 10,292 | 3 | 0.889 | 0.670 | model | 227 / 169 of 1,441 | 0.834 (3) | 40 |
| Chico | 2,313 | 3 | 0.885 | 0.638 | model | 96 / 61 of 197 | too few | 11 |
| San Diego | 19,467 | 3 | 0.880 | 0.653 | model | 264 / 212 of 2,438 | 0.815 (3) | 47 |
| Cupertino | 990 | 2 | 0.880 | 0.702 | mixed | 67 / 53 of 101 | too few | 4 |
| South Lake Tahoe | 820 | 1 | 0.876 | 0.529 | blend | 37 / 9 of 55 | too few | 1 |
| Ventura | 2,261 | 3 | 0.872 | 0.667 | model | 197 / 163 of 469 | 0.833 (1) | 13 |
| Encinitas | 1,299 | 3 | 0.872 | 0.659 | mixed | 90 / 69 of 178 | 0.806 (1) | 22 |
| Davis | 1,114 | 3 | 0.870 | 0.757 | model | 128 / 115 of 217 | too few | 9 |
| Palo Alto | 1,288 | 2 | 0.869 | 0.737 | model | 78 / 68 of 169 | 0.814 (1) | 9 |
| Sunnyvale | 1,989 | 3 | 0.865 | 0.666 | model | 104 / 74 of 256 | too few | 10 |
| Long Beach | 5,151 | 3 | 0.864 | 0.702 | model | 348 / 315 of 1,543 | 0.778 (3) | 47 |
| Fresno | 11,648 | 3 | 0.863 | 0.553 | mixed | 73 / 52 of 533 | 0.791 (1) | 12 |
| Santa Barbara | 1,594 | 3 | 0.862 | 0.703 | model | 254 / 216 of 628 | 0.814 (2) | 14 |
| Oakland | 5,667 | 3 | 0.861 | 0.688 | model | 205 / 165 of 1,022 | 0.758 (2) | 17 |
| San Francisco | 7,094 | 3 | 0.855 | 0.744 | model | 752 / 694 of 3,636 | 0.750 (2) | 25 |
| Santa Cruz | 1,108 | 3 | 0.840 | 0.719 | model | 195 / 174 of 384 | 0.794 (1) | 9 |
| Redwood City | 1,397 | 3 | 0.834 | 0.630 | model | 110 / 88 of 272 | 0.783 (1) | 16 |
| Mountain View | 1,030 | 3 | 0.830 | 0.659 | model | 133 / 92 of 242 | 0.776 (1) | 18 |
| Los Altos (alone) | 806 | 2 | 0.822 | 0.671 | blend | 40 / 31 of 72 | too few | 9 |
| San Mateo | 1,519 | 2 | 0.805 | 0.571 | blend | 47 / 30 of 137 | too few | 8 |
| Menlo Park | 675 | 3 | 0.804 | 0.685 | mixed | 111 / 97 of 170 | too few | 18 |
| Berkeley | 1,437 | 3 | 0.795 | 0.686 | model | 244 / 234 of 796 | 0.742 (2) | 22 |
| Santa Monica | 895 | 3 | 0.783 | 0.670 | model | 142 / 119 of 352 | too few | 8 |
| East Palo Alto | 279 | 2 | 0.744 | 0.622 | blend | 52 / 42 of 70 | too few | 4 |
| Los Altos Hills | 372 | 0 | too few | too few | blend | – | too few | 0 |

The ranking beats history alone in every city scored, on both measures. Los
Altos Hills has 19, 13 and 12 later crashes in its windows and no score at
all; South Lake Tahoe is scored on one window, of 55 later crashes, so its
0.876 rests on far less than its neighbours in the table. Santa Monica's
police have no injury crash on record for the whole of 2020 (about 440 in a
typical year), so its first window is tested on little more than three years of crashes
instead of four and its later windows are fitted with a year missing; the reporting check
marks the year. CCRS holds 8 crashes of any kind under that department's code in 2020,
whatever the city, against 864 in 2019 and 891 in 2021; all 8 are under
Santa Monica. Records filed under another agency's code were not looked for. Of the 46 Los Angeles County agencies with
200 or more crashes in CCRS in 2019, it is the only one whose 2020 count is
under a tenth of that. The gap falls where the department's reports change
format (the earlier format to the end of 2019, the CCRS one from 2021); why
the injury-crash records are missing has not been confirmed.

A score that rests on few later crashes is uncertain: by the Hanley–McNeil
formula, one standard error at a score of 0.8 is about 0.08 with 10
intersections that had a later crash and about 0.05 with 30, which is as
large as most differences in this note. Only Irvine, Huntington Beach, San
Jose, Sacramento, San Diego and Long Beach have 30 or more later child crashes
in every window; eleven cities have none that can be scored for children. No intervals
were computed for the figures in the table.

## Where it helps most

- **Spread-out cities built on arterials.** San Jose, Sacramento, San Diego,
  Irvine, Huntington Beach, Chico and Fresno score highest or gain most over
  history.
  Bike crashes there follow car traffic, which the model reads from car
  crashes and street length. In San Jose and Sacramento the top 100
  intersections hold about 35% more later crashes than history alone finds,
  and in San Diego 25% more.
- **Intersections with no bike crash on record.** Most intersections have
  none, yet between a quarter and 70% of later bike crashes happen at them,
  depending on the city and window (twelve cities compared). History cannot order them at all; the model can.
- **Cities with little bike history per corner.** Fresno's history alone
  scores 0.553; the model scores 0.863.
- **Children, in the large cities.** With 40 or more later child crashes a
  window, San Jose and Sacramento score 0.83 to 0.84 and are steady from window
  to window; San Diego scores 0.82.

## Where it helps least

- **Where cycling is separated from car traffic (a hypothesis, from one
  city).** Berkeley scores lowest but one of
  the cities large enough to fit the model in every window (Santa Monica is
  lower; see the simulation), and at its top 25 intersections
  the model finds little more than history does (88 later crashes against 85).
  It has 0.4 to 0.5 bike crashes per car crash where other cities have 0.1 to
  0.35, and car crashes alone rank its later bike crashes worse than in any
  of the nine other cities first compared. The model expects too many bike crashes on the car
  arterials (Ashby: 57 expected, 24 recorded, over two windows) and too few on
  quieter streets cyclists use (Milvia, a bicycle boulevard: 42 expected, 55
  recorded). It is not a clean split: California Street, also a bicycle
  boulevard, was over-predicted. Across cities, how well the model ranks
  tracks how well car crashes alone rank (correlation 0.84 over ten cities and
  two windows).
  A simulation (under "What the rank score does and does not tell you")
  finds that most of Berkeley's distance from the other cities is what the
  model's own rates predict, and that its real score falls about 0.02 short
  of that. The simulation does not say what causes the shortfall.
  Menlo Park shows the same pattern. Santa Cruz, another cycling city, scores
  0.840, in the lower third, but was not examined in this way. Davis, looked at
  later, shows that a cycling city can score highly despite a weak car-only
  ranking: car crashes alone rank its later bike crashes about as poorly as
  Berkeley's (0.65, 0.67 and 0.73 over the three windows, against 0.69, 0.67
  and 0.71), and the model scores 0.870 there. Whether cycling in Davis is
  separated from car traffic in the way suggested for Berkeley was not
  examined.
- **Where history is already rich.** In San Francisco history alone scores
  0.744 and the model's top 100 holds only 8% more later crashes (752 against
  694). The model is still better down the list. Davis and Palo Alto are
  similar.
- **At the very top of the list.** Past bike crashes alone match or beat the
  model at the top 25 in Encinitas and Menlo Park.
  The model's gain is mostly further down.
- **Very small cities.** Los Altos Hills (372 intersections) and East Palo
  Alto (279) have too few crashes to fit the model. East Palo Alto scores
  lowest, and Los Altos Hills has too few later crashes to be scored at all.
  See pooling, below.
- **Children, in most cities.** Twenty-two of the 28 cities have a window with
  fewer than 30 later child crashes, and most cannot fit the model for
  children at all.

## What the rank score does and does not tell you

- **It rewards ordering the whole list, not the top.** Much of a 0.85 comes
  from putting the many quiet corners below the busy ones. For "where to look
  first", read the top-25/50/100 counts as well: run the hold-out with `--out`
  and see the `found in top …` columns of the file it writes.
- **Much of it is exposure.** In an earlier one-off run on the Los Altos
  study area (its script is not included), street length alone scored 0.849 against the model's 0.856 (see
  "What each choice contributes" in the method note).
- **It ignores the level.** A forecast wrong by a factor of two everywhere
  scores the same.
- **It is not comparable across cities.** It depends on how varied a city's
  streets are and on how its crashes are spread among them, so a lower score
  in one city is not by itself a worse ranking. Berkeley has a later bike
  crash at 15% to 18% of its intersections, the most of any city.

  A simulation shows how much this matters. For each intersection, draw a
  rate from the fitted model's distribution for it (the gamma blend of the
  model's expectation and the corner's own count), scaled so that the
  expected later total equals the recorded one; draw a Poisson count of later
  crashes from that rate; and score the model's ranking on the result. The
  mean over 2,000 such replicates per window is the score the ranking would
  expect if the model were exactly right about the city. The fitted
  parameters are taken as known.

  | City | Rank score, three windows | Mean simulated score | Share of simulations below the real score |
  |---|---|---|---|
  | Berkeley | 0.804, 0.787, 0.791 | 0.806, 0.811, 0.819 | 43%, 10%, 2% |
  | Huntington Beach | 0.902, 0.886, 0.897 | 0.891, 0.901, 0.897 | 82%, 12%, 49% |
  | Oakland | 0.856, 0.864, 0.851 | 0.844, 0.846, 0.854 | 87%, 91%, 36% |
  | San Francisco | 0.847, 0.855, 0.859 | 0.856, 0.863, 0.863 | 10%, 17%, 30% |
  | Santa Cruz | 0.839, 0.850, 0.831 | 0.834, 0.839, 0.837 | 60%, 66%, 38% |
  | Long Beach | 0.858, 0.864, 0.866 | 0.848, 0.859, 0.867 | 86%, 66%, 46% |
  | Davis | 0.874, 0.875, 0.856 | 0.872, 0.879, 0.879 | 50%, 42%, 14% |
  | Santa Monica | 0.783, 0.759, 0.804 | 0.775, 0.783, 0.791 | 62%, 19%, 74% |
  | San Diego | 0.873, 0.881, 0.881 | 0.866, 0.873, 0.877 | 85%, 82%, 75% |

  Berkeley is about 0.10 below Huntington Beach, and the simulated scores
  differ by about 0.085: under the fitted model, its own ranking has a lower
  expected score in Berkeley, where the fitted risk is spread more evenly
  over more corners. Berkeley's real score is below the simulated mean by
  0.002, 0.024 and 0.028, about 0.018 on average. In its last window only 2%
  of the replicates score as low; that is one of 27 city-windows looked at,
  the windows overlap, and nothing was adjusted for that, so read it as a
  pointer. The other cities fall on both sides of their simulated means; San
  Francisco is a little below in all three windows (0.004 to 0.009) and San
  Diego a little above in all three (0.004 to 0.008). Santa Monica, a compact
  city with a later bike crash at 7% to 14% of its intersections, scores
  lower than Berkeley and within 0.001 of its simulated mean on average
  (0.008 and 0.013 above it in two windows, 0.024 below in one): its mean
  score is close to the simulated mean under the fitted model. Its 2020
  police injury-crash records are missing (see the results), which the simulation does
  not allow for. Davis, another cycling city, has a high simulated score and is within
  0.004 of it in two windows of three (0.023 below in the third): a cycling city can score highly. The
  simulation takes the fitted model as the truth, so it cannot say whether
  risk in Berkeley really is that evenly spread or the model fails to see
  differences that are there, and it does not show how well another ranking
  could do.
- **A fixed top 100 is not comparable either**: it is 1% of Fresno's
  intersections and 36% of East Palo Alto's.

## Limits, and how to work around them

### Too few crashes to fit the model: pool with similar neighbours

Fit on the city together with its neighbours, then report inside the city.
The Los Altos case study does this with a study area; the pooled configs
(`config/pool_*.yaml`) do it with whole neighbouring cities, each scored inside
its own limit with the hold-out's `--city-limit`.

Mean rank score over the windows scored, inside the city. "Too few" means no
window had 30 later crashes. The Santa Clara County cities are shown in the
pool without San Jose:

| City | All cyclists, alone | Pooled | 18 or under, alone | Pooled |
|---|---|---|---|---|
| Berkeley | 0.795 | 0.790 | 0.742 | 0.780 |
| Oakland | 0.861 | 0.859 | 0.758 | 0.752 |
| East Palo Alto | 0.744 | 0.776 | too few | too few |
| Menlo Park | 0.804 | 0.798 | too few | 0.712 |
| Redwood City | 0.834 | 0.837 | 0.783 | 0.787 |
| Cupertino | 0.880 | 0.901 | too few | too few |
| Los Altos | 0.822 | 0.838 | too few | too few |
| Los Altos Hills | too few | too few | too few | too few |
| Mountain View | 0.830 | 0.827 | 0.776 | 0.819 |
| Palo Alto | 0.869 | 0.864 | 0.814 | 0.831 |
| Sunnyvale | 0.865 | 0.865 | too few | too few |

- Cities that cannot fit the model in every window when alone gain: East
  Palo Alto 0.032, Cupertino 0.021 and Los Altos 0.016. Menlo Park, fitted in
  some windows, is the exception (down 0.006).
- Cities that fit the model alone are unchanged, within 0.005 either way.
- A bigger pool is not better: adding San Jose to six Santa Clara County
  cities moved none of them by more than 0.006.
- Pooling does not fix a city whose trouble is not sample size (Berkeley).
- Los Altos Hills has too few later crashes to be scored either way, so the
  test cannot say whether pooling helps it. That is a limit of the test and
  not a reason against pooling it.
- Child scores exist both ways in five cities and rise in four of them
  (Mountain View by 0.043, Berkeley by 0.038, Palo Alto by 0.017, Redwood
  City by 0.004; Oakland falls by 0.006). Each rests on one or two windows.
- No intervals were computed and no difference here has been shown to be
  outside the noise. All-cyclist scores rise in four cities, fall in five
  and are level in one.

Two cautions. Pool with cities that resemble yours: South Lake Tahoe has no
such neighbour. And a pool mixes police departments, so a change in one
department's reporting distorts a ranking across the pool (see the method
note): run the reporting check on the pool, and score or publish inside each
city. A pool cannot yet cross a county line.

**Setting up a pool.** A pooled area is an ordinary config, built with the
same commands as a city. The folders are not chosen from the config's name,
so pass them, and name the processed folder after the config, which is where
the cross-city command looks:

```bash
P=pool_san_mateo
uv run python -m bike_safety_ca.network --config config/$P.yaml \
    --raw data/raw/$P --out data/processed/$P
uv run python -m bike_safety_ca.crashes download --config config/$P.yaml \
    --raw data/raw/$P/crashes --out data/processed/$P/crashes
uv run python -m bike_safety_ca.crashes --config config/$P.yaml \
    --raw data/raw/$P/crashes --out data/processed/$P/crashes
```

1. **Config.** Start from an existing `config/pool_*.yaml`, or from a member
   city's config with any setting that draws its own area removed
   (`area_file`, `area_schools`, `area_points`, `area_points_file` and
   `area_buffer_m`; the Los Altos config has some of them).
   List every member under `ccrs_cities`: the area fitted is then those
   cities' Census limits joined together, and the CCRS download fetches all
   of them. `city` names one member; it is a label, and the city whose limit
   the hold-out scores by default when run on the pool by hand. All members
   must be in the one county given by `ccrs_county_code`, and the `latitude`
   and `longitude` box must cover them all.
2. **TIMS.** The crash step reads every batch folder under the pool's TIMS
   folder and joins them, whatever cities each holds. If you export the
   cities one at a time, as the TIMS query form invites, put each export's
   three files in a batch folder of its own, for
   example `data/raw/<pool name>/crashes/tims/menlo_park/` and
   `.../tims/redwood_city/`. A link does as well as a copy, if it points at the folder
   that holds the three files and not at its parent. Two things depend on
   the folder's name (the link's name, for a link): a name containing
   "provisional", in any case, marks its crashes as provisional, and a crash
   that appears in two folders is taken, with its parties and victims, from
   the one whose name sorts last. Exports of different cities do not share
   crashes, so for them the order does not matter.
3. **Members.** Build each member city on its own as well, under its own
   config, with the pool's `child_max_age`. The cross-city command (see "What
   was run") fits each config named with `--pool` as a whole and scores it
   inside the limit of every city built alone that lies in it, beside that
   city's score when fitted alone. Membership is by the map, not by
   `ccrs_cities`: a city is a member when at least 95% of its limit (or of
   the area it was fitted on, if it has no limit) is inside the pool's area.

### Too few child crashes: rank children by the all-cyclist ranking

Two different shortages are easy to confuse.

**Too few later crashes to score.** A rank score on a handful of later
crashes is close to those crashes' own ranks. The hold-out leaves a window
with fewer than 30 later crashes unscored. This says what the test can show.
It does not say the ranking is no good there, and it does not stop you
ranking: a small city's intersections are part of the wider area's test, and
that is the evidence for them. In the Los Altos case study the child ranking
scores 0.854 over the study area, on 87, 40 and 76 later child crashes. Inside
the city limit the windows hold 18, 9 and 18, so the city has no child score
of its own, and the study-area score is the one to quote.

**Too few child crashes to build a child ranking from.** This is about the
training years. Each city's hold-out now has an "All-cyclist ranking" row
for children: the ranking fitted to every cyclist crash, scored on later
child crashes. Taking the 33 city-windows with 30 or more later child
crashes, from 28 cities fitted alone:

| Child crashes in the training years | City-windows (cities) | Ranking fitted to child crashes | All-cyclist ranking | Child ranking better in |
|---|---|---|---|---|
| Under 100 | 15 (12) | 0.789 | 0.812 | 0 |
| 100 or more | 18 (7) | 0.833 | 0.835 | 10 |

Under 100 child crashes, which is where the model cannot be fitted and the
blend is used, the child ranking loses to the all-cyclist ranking
every time. At 100 or more the two are level (San Diego, the largest city
tried, included: 0.815 against 0.822 over its three windows). Nowhere in these cities does a
separate child ranking clearly beat the all-cyclist one.

So:

- **Fit wide, report inside the city.** A study area or a pool of similar
  neighbours gives the fit enough child crashes; read the ranking inside your
  own limit. Pooling raised child scores in four of the five cities where
  one could be scored both ways.
- **With under 100 child crashes in the area you fit, rank children by the
  all-cyclist ranking**, and say plainly that there were too few records to
  rank children on their own. A missing child ranking should not read as "no
  risk to children here". The hold-out prints this advice under its table.
- **With 100 or more, either ranking will do.** The Los Altos study area has
  174 to 261 child crashes in its training years and its two rankings are
  level (0.854 and 0.851).
- **Quote the test of the area you fitted,** not a score for a part of it that
  has too few later crashes to carry one.

### Police reporting changes: check before believing a trend

Several cities show jumps in a department's yearly injury-crash counts that
look too large and too sudden to be changes in safety. None has been confirmed
with the department; each is a reason to look into its reporting:

- Fresno police injury crashes: 844 in 2015, then 171, 47, 21 and 192, then
  848 in 2020.
- Palo Alto police: over 300 a year to 2019, then 80, 8, 29 and 16 in
  2022–2025.
- San Mateo police: 6 and 13 in 2015–2016, about 250 a year after.
- Chico police: 244 in 2022, 130 in 2023.
- Santa Cruz police: about 255 a year in 2015–2017, 164 in 2018, and lower
  since.
- South Lake Tahoe police: about 20 a year to 2019, 70 to 86 from 2022.

Run the reporting check first (`python -m bike_safety_ca.checks.reporting
--config config/<city>.yaml --crashes <crash folder> --out <folder>`; see the
guide). It compares each agency's year with that agency's own typical year,
marks a fall (under 0.4 of it), a rise (over 2.5 times) or a possible one
(under 0.6, over 1.67 times), and uses the other agencies only to excuse a
move they share.

The first version of the rule divided each agency's change by the other
agencies' change. Run on single cities, where "the others" is often one
agency, it flagged the wrong agency and missed most of the changes above.
The rule was rewritten, and on the same crash tables (injury crashes) it now
gives:

| Agency | First rule | Now |
|---|---|---|
| Fresno police | 2018 only | fall 2016–2019 |
| Fresno, highway patrol | 2020–2023 (the police's recovery) | nothing |
| San Mateo police | nothing | fall 2015–2016 and 2022, possible fall 2021 |
| San Mateo, highway patrol | 2018 | nothing |
| Palo Alto police (in the Los Altos study area) | 2022–2025 | fall 2022–2025, possible fall 2026 |
| Chico police | nothing | possible fall 2023 |
| South Lake Tahoe police | nothing | rise 2022–2025, possible rise 2021 |
| Mountain View police | 2022 (the highway patrol's rise) | nothing |
| Santa Cruz police | 2019 | possible fall 2020 |

What it still does not catch:

- **A lasting step smaller than the lines.** Santa Cruz police settle in 2018
  at about 0.64 of their earlier level; no single year is marked for it.
  Mountain View's highway patrol count in 2022 is 1.5 times its usual. The
  table of lasting changes, below, lists both, because over all the years
  after the step each is past its line (Santa Cruz 254 → 145 a year, Mountain
  View's highway patrol 132 → 232). A step that stays inside 0.6 to 1.67
  times the old level is in neither list.
- **A steady decline.** Sacramento's highway patrol count falls over the
  whole period; 2015–2016 are marked as possible rises and 2025–2026 as
  falls, because the typical year sits in the middle.
- **A real fall with no one to compare with.** Where one agency reports
  nearly everything, 2020 is marked for cyclist crashes in eight of the
  28 cities, as a fall in three of them. One of the three is Santa Monica,
  where the mark is right: its police have no injury crash on record that
  year.
- **Cyclist crashes in small agencies.** An agency needs a typical year of 8
  cyclist crashes to be judged at all.

So read the yearly tables the check writes, and not only its flags.

### Minor-injury reports fall in many departments while the total holds

The check also writes a table of lasting changes of level
(`level_steps.csv`): an agency whose yearly count settles under 0.6 of its
old level or over 1.67 times it, in all injury crashes or at one severity,
with at least three finished years on each side. The figures here and in the
next section come from the command under "What was run", on the 28 cities
(the pooled areas are not counted, so that each city counts once).

Over 2015 to 2025, 18 of the 28 cities have at least one agency with a step,
25 agencies in all:

| Measure | Fewer reports | Regraded | More reports |
|---|---|---|---|
| All injury crashes | 5 | – | 3 |
| Complaint of pain | 13 | 4 | 2 |
| Visible injury | 2 | 3 | 3 |
| Serious injury | 0 | 0 | 6 |

"Regraded" means the agency's other severities changed the opposite way by a
half to twice as much, so the crashes are probably still reported at another
severity. The steps in "complaint of pain" crashes, the least serious grade
(typical year before → after):

| Agency | From | Complaint of pain | Other severities | Read as |
|---|---|---|---|---|
| Menlo Park police | 2018 | 110 → 23 | 62 → 93 | fewer reports |
| Redwood City police | 2018 | 222 → 53 | 105 → 167 | fewer reports |
| Berkeley, highway patrol | 2018 | 105 → 59 | 31 → 34 | fewer reports |
| Santa Monica, highway patrol | 2018 | 87 → 46 | 27 → 29 | fewer reports |
| Berkeley police | 2019 | 333 → 103 | 200 → 411 | regraded |
| Ventura police | 2019 | 329 → 162 | 210 → 328 | regraded |
| Santa Cruz police | 2019 | 120 → 38 | 132 → 99 | fewer reports |
| Cupertino (sheriff) | 2019 | 86 → 34 | 49 → 42 | fewer reports |
| Davis police | 2020 | 45 → 20 | 69 → 108 | regraded |
| Irvine police | 2020 | 376 → 179 | 231 → 262 | fewer reports |
| Encinitas, highway patrol | 2020 | 71 → 40 | 31 → 28 | fewer reports |
| Cupertino, highway patrol | 2020 | 62 → 36 | 29 → 20 | fewer reports |
| Sacramento, highway patrol | 2020 | 178 → 55 | 102 → 41 | fewer reports |
| Mountain View police | 2022 | 120 → 32 | 94 → 145 | regraded |
| Palo Alto police | 2022 | 222 → 6 | 127 → 17 | fewer reports |
| San Jose, highway patrol | 2022 | 27 → 8 | 22 → 7 | fewer reports |
| Chico police | 2023 | 107 → 40 | 130 → 121 | fewer reports |

Fresno and South Lake Tahoe police show rises, part of the changes in their
totals listed above. In Menlo Park and Redwood City the other severities rise
by about a third of the fall, under the half that the table calls regrading,
so those are probably a mix of the two.

Only five of these 17 agencies have a step in their total, so the yearly flags
on totals miss most of them. None of these steps has been confirmed with a
department, and 2020 is a year when crashes really fell.

**Should the ranking leave minor crashes out, then?** No, on this evidence.
The sensitivity command builds the ranking twice per window, from all injury
crashes and from crashes with a visible injury or worse (bike and car
crashes alike), and scores both on later cyclist crashes of each kind. Over
the 71 windows in 26 cities that had 30 later crashes of both kinds (of the
28 cities, East Palo Alto and Los Altos Hills had too few):

| Mean rank score on later cyclist crashes | Trained on all injury crashes | Trained on visible injury and worse |
|---|---|---|
| All injury crashes | 0.857 | 0.843 |
| Visible injury and worse | 0.852 | 0.839 |

The ranking trained without minor crashes is worse in 69 of the 71 windows
on all later crashes and in 68 on the visible-and-worse ones, by 0.01 to 0.02
in most cities and up to 0.05 in one window. The 15 cities with a lasting
fall in "complaint of pain" reports lose a little more (0.016 on average)
than the 11 without (0.011).

Part of that is not a fair comparison. Without the minor crashes a city
sooner has too few to fit the model and the ranking falls back to the
hand-built blend. In 8 of the 71 windows only the ranking without them fell
back, and there it loses 0.03. In the 54 windows (21 cities) where both
rankings came from a fitted model it loses 0.011 on all later crashes and
0.010 on the visible-and-worse ones, and is worse in 53 and 51 of them. So
the loss is small, but it is there on equal terms: minor crashes still help
to find where the later serious ones happen, and the ranking keeps them.

What this does not settle: counts are still not comparable across a step,
between years or between cities, and a ranking pooled over several cities
gives more weight to the ones that file more minor crashes. The later
crashes used for scoring are affected by the same reporting changes.

Every city's last year is incomplete, and TIMS lags CCRS: in the cities
checked, a third or more of 2026 crashes were in CCRS only.

### Where cycling is separated from car traffic: no workaround yet

Berkeley's shortfall against the model's own simulated score is small (about
0.02 of rank score, see above), but the misplaced streets are specific. If the Berkeley
reading is right, the model needs a measure of where people
ride, such as a bike-route layer, or a weight on car crashes that can differ
by city. Neither has been tried. The hold-out does not yet report how car crashes
alone rank later bike crashes, which is the figure that set Berkeley apart.
Until then, in a city where many people ride on streets away from the main
car routes, treat the ranking of the car arterials with caution and look at
the bike history of the quieter streets yourself.

### Crashes that cannot be placed

Between 1% and 21% of a city's crashes have no usable location and are left
out (East Palo Alto 21%, Huntington Beach 15%, Long Beach 13%). If the
unplaced crashes cluster on particular streets, those streets are
under-ranked. This has not been examined.

### City names the Census writes differently

The area step looks each city up by name in the Census place file and stops
if it is not there, naming the closest places it does have. Ventura is "San
Buenaventura (Ventura)" in that file and Paso Robles is "El Paso de Robles
(Paso Robles)": a city written this way is found by the name in brackets, by
the formal name before them, or by the whole thing, and its streets carry the
name in brackets, which is the one crash reports use. Other differences
(hyphens, "St." against "Saint", accents) have not been looked for.

### When the street download fails

The public Overpass servers were unavailable for much of the test, and
refused San Diego's area outright. The
network step uses a street file that is already in place, so the streets can
be cut from a regional OpenStreetMap extract instead and saved in the same
form, with the metadata note the download writes. Cut from an extract a day
older than the server's copy, Mountain View's streets differed only by that
day's edits.

## Data credits

Crash figures here are built from two sources:

- Transportation Injury Mapping System (TIMS), Safe Transportation Research
  and Education Center, University of California, Berkeley.
- California Crash Reporting System (CCRS), California Highway Patrol, via
  data.ca.gov.

Street data © OpenStreetMap contributors, ODbL 1.0. See "Crash
records" in `docs/guide.md` for each source's terms.
