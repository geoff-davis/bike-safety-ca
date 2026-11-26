# Guide

How to run each part of bike-safety-ca, from the demo city to your own crash
records. The [README](../README.md) says what the parts are for.

## Try it without any data

```bash
uv sync
make walkthrough
```

This opens `notebooks/walkthrough.py`, a [marimo](https://marimo.io) notebook
that runs every step in order on a demo city: the area and its intersections,
the crash tables, the reporting check, the hold-out test, the ranking and the
movement map. Each step calls the same code as the command line.

The demo city has **real streets and made-up crashes**. The streets are
Claremont, California, from OpenStreetMap; the city was picked only because it
is small and far from the case study. `python -m bike_safety_ca.demo` invents
every crash and party from round-number settings, fitted to no police records,
and marks every case number `SYN-`. Charts and the map made from it are
labelled as synthetic. Because the demo knows each intersection's true crash
rate, the notebook can score the ranking against the truth. It also plants
three changes in police reporting for the reporting check to find.

To use the notebook on your own city, build your tables with the commands
below and put your config file's path in the box at the top.

`make demo` is a quicker check with no map at all: it builds a made-up grid
city, fits each ranking on its early years and scores it on the later ones. A
rank score of 0.5 is a coin toss; 1.0 is perfect.

## Use it on your own counts

```python
from bike_safety_ca.model.crash_history import rank_intersections

ranked = rank_intersections(bike, car, streets)
ranked["score"]    # rank intersections by this
ranked["method"]   # "street-length model" or "hand-built blend"
```

`bike` and `car` are pandas Series of crash counts indexed by intersection.
`streets` maps each intersection to the names of the streets that meet there.
For a city whose tables you have built, `python -m bike_safety_ca.model`
makes these inputs and writes the ranking (see "The intersection ranking").

With fewer than 100 bike crashes in all there is too little to fit the model, so
the ranking falls back to a hand-built blend of the same inputs that needs no
fitting. The model's score is an expected number of crashes; the blend's only
puts intersections in order.

To rank where children are hit, pass child crashes as `bike` only if the area
has about 100 or more of them. With fewer, use the all-cyclist ranking and say
so: across the test cities a ranking built from under 100 child crashes found
later child crashes less well than the all-cyclist ranking did (see
`docs/where_the_ranking_helps.md`). A small city can still get a child
ranking by fitting on a wider area around it and reading the result inside
its limit, as the Los Altos case study does.

## Using it for your city: the steps in order

1. Write a config for the city (see "Building the crash tables" for the
   settings to change).
2. Build the area and its streets.
3. Export the crashes from TIMS and build the crash tables.
4. Check for changes in police reporting.
5. Check the ranking on later crashes, then write the ranking.
6. Make the corridor table, the summaries and the crash map.

The sections below follow this order. The streets come before the crashes
because crashes with no coordinates are placed from the street table unless
you give a road-centerline layer.

## The area and its streets

```bash
uv run python -m bike_safety_ca.network --config config/los_altos.yaml
```

This draws the outline of the cities listed in the config from Census
boundary files, fetches the streets inside it from OpenStreetMap (the public
servers can take half an hour, or refuse and need a second try), and builds
the street table. If "Unincorporated" is in the city list, the outline also
takes in the unincorporated pockets between and beside the listed cities, not
the whole unincorporated county. To use your own outline instead, pass
`--area` (GeoJSON, shapefile or GeoParquet) here and to the checks below.

If the public servers refuse the area, or you would rather not load them, cut
the streets from a regional OpenStreetMap extract instead:

```bash
uv sync --extra extract
uv run python -m bike_safety_ca.network --config config/san_diego.yaml \
    --extract path/to/socal-latest.osm.pbf
```

Geofabrik publishes extracts of Northern and Southern California
(download.geofabrik.de, under North America, United States, California). The
cut is written in the same form as a download, with a note naming the
extract, and it takes the ways that touch the area's padded box, as the
server does: cut from an extract three days newer, Santa Monica's 26,309
saved ways were all there, plus one. It holds the map of the extract's date,
so a config that pins `osm_date` (as `config/los_altos.yaml` does) refuses
it. Reading a regional extract takes
about half a minute and 2.5 GB of memory.

## Building the crash tables

```bash
uv run python -m bike_safety_ca.crashes download --config config/los_altos.yaml
uv run python -m bike_safety_ca.crashes --config config/los_altos.yaml \
    --centerlines path/to/road_centerlines.parquet
```

- `download` fetches CCRS crash, party and injured-person records for the
  config's county and cities from data.ca.gov into `data/raw/crashes/ccrs/`.
- TIMS exports are made by hand (a free account at tims.berkeley.edu) and go in
  `data/raw/crashes/tims/<batch>/` as `Crashes.csv`, `Parties.csv`, `Victims.csv`.
  Every batch folder is read and joined, so an area of several cities can
  take one folder per city's export (see "Setting up a pool" in
  `docs/where_the_ranking_helps.md`).
- The second command reads the TIMS exports, merges CCRS into them, flags
  duplicate reports and reporting gaps, and writes tables to
  `data/processed/crashes/`. With a road-centerline layer it also places
  crashes that have no coordinates from the cross streets the report names.
- Each download records the request it was fetched for, and is reused only
  for that request. If the config's cities, area or map date change, the
  command stops and asks for another folder or `--overwrite`. A file saved
  without such a record (by hand, or by an older version) is used as it is,
  with a warning.
- CCRS gives the Vehicle Code section an officer cited but not the cause
  category TIMS has. The merge takes, for each section, the category TIMS
  gives it in at least 90% of the rows that cite it, and marks those rows
  `cause_category_inferred`. Sections it cannot place stay "Other / unknown".
- When two reports from one agency match a TIMS crash equally well, the
  nearer one is linked, and a report more than 1 km away loses to any within
  1 km. A report that shares both street names and has no rival within 1 km
  is linked whatever the distance; the merge report counts those more than 1 km
  apart, where one of the two coordinates is wrong. Two different TIMS
  crashes that match one CCRS report equally well are both left unlinked.
- A CCRS report number used again within 60 days replaces the earlier report
  only when the crash dates are within a day or the reports share a street.
  Otherwise both are kept and marked `report_number_conflict`.
- Two agencies' reports of one crash are flagged as possible duplicates and
  left out of counts, unless one lists a cyclist or pedestrian and the other
  does not, or both do and the recorded sexes or ages show different people.
  The pairs are in `crashes_duplicate_reports.csv`; read them if the count
  matters.
- The merge reads only the CCRS files the last download listed, and stops if
  that download was made for other cities than the config's.
  A download that stopped part-way says so in its list, and the merge then
  warns that later years are missing; run `download` again.
- A TIMS crash whose case number names a CCRS report dated more than a day
  away is not linked to it (`case_id_date_mismatch`; `ccrs_tims_links.csv`
  gives the report in `date_mismatch_ccrs_id`). When the two share both
  street names, lie within 150 m, or share one name and lie within 1 km
  (`date_mismatch_corroborated`), the CCRS report is marked a possible
  duplicate of the TIMS row. That needs exactly one such TIMS row that is
  not itself a possible duplicate, and the row must have a date, and a
  point unless the report has none. With several rows, which may be
  different crashes, or a row lacking either, every row is counted, and
  nothing is ever copied from the report to the TIMS row.
  `crashes_merge_report.json` counts each case
  (`ccrs_only_flagged_for_case_id_date_mismatch`,
  `case_id_date_mismatches_kept_as_two_crashes`,
  `case_id_date_mismatches_with_several_tims_rows_kept`,
  `case_id_date_mismatches_kept_because_tims_row_incomplete`) and the CCRS
  injury crashes
  with no injury grade (`ccrs_injury_crashes_without_severity`).
- A cyclist crash with no age recorded counts toward "all cyclists" but not
  toward the child figures, which cover known ages only. Records found only in
  CCRS often lack an age, so check how many there are (the yearly summary has
  a column for them) before reading a trend in child crashes.

`config/los_altos.yaml` holds every local choice. To use it for another city,
copy it, edit `city`, `county`, `crs`, `ccrs_county_code`, `ccrs_cities` and
the `latitude` and `longitude` box, and delete the settings that are Los
Altos's own (`agency_reassignments`, `municipality_aliases`, `city_limit_url`,
`area_schools`, `area_points`, `area_buffer_m`, `osm_date`); left in, they
would build your study area around Los Altos.

Things the code assumes, which may not hold for your city:

- `crs` must be a projected coordinate system in metres. Every distance rule
  (35 m to an intersection, 25 m between joined corners) is in metres, and the
  config is refused otherwise.
- Building from CCRS alone is not supported yet: the merge step needs a TIMS
  export.
- Crash reports are matched to streets with directions and street types
  dropped, because police abbreviate them and leave them out: a report of
  "N Main St" or "Main Ave" fits Main Street. The model and the corridor
  table keep the street type, so Park Avenue and Park Place are two streets;
  a report that says only "Park" goes to the nearer corner, or between
  corners to the longer street. El Camino Real is treated as
  State Route 82, which is true on the San Francisco Peninsula; elsewhere the
  two names simply share one label.
- A report's "150 feet north of Oak" is measured as a compass offset onto the
  named road, not as a distance travelled along it, so a crash on a curving
  or diagonal road can sit some metres off.
- The school-commute flag in the summaries takes the summer break from
  `summer_break` (default 8 June to 14 August) and knows no other holidays.
- `agency_reassignments` rules apply to every year unless given a `from_year`.
- The group names say "18 or under"; printed tables follow `child_max_age`.
- "In the city" means two things: the summaries use the city named on the
  report, the hold-out uses the city-limit outline. The counts can differ.
- The `latitude` and `longitude` box is applied to CCRS coordinates only; TIMS
  coordinates are used as given.
- Use a separate `--out` folder for each city. The merge report records the
  city the crash tables were built for, and the notebook refuses tables built
  for another city; the command-line checks do not look.
- Crashes with no coordinates are placed from the two street names on the
  report. So are crashes whose CCRS point is over 1 km from both streets
  the report names: some early CCRS years hold points tens of kilometres
  off. Such a crash keeps its point when the street names cannot place it,
  and TIMS points are kept as given. The merge report counts both.
- The street names are looked up in `--centerlines` when you give one (a
  county road-centerline layer with `STNAME`, `FULLNAME` and `MUNICIPALI`
  columns). Otherwise they are looked up in the OpenStreetMap street table,
  so run the network command first. With neither, those crashes stay as
  they are.
- Street names are matched loosely ("Oak Street" and "Oak Avenue" are one
  name), and the street table is matched as drawn lines, so two streets that
  cross on a bridge look like an intersection. A crash is placed where the
  two names cross at one place in the report's city (crossings all within
  60 m of each other, as on a divided road, count as one place), or where
  they pass within 15 m without crossing. A looser second pass accepts a
  cross street that stops up to 60 m short of the other road. Section 8.5 of
  `docs/forecasting_model.md` gives the rules in full.
- With `--area`, the network command still builds the config's own outline
  first, so the Census files are fetched anyway.
- The licence here covers the code. TIMS and CCRS data have their own terms
  (see "Crash records"), and nothing here gives a right to pass on the crash
  tables.

## Check for changes in police reporting first

```bash
uv run python -m bike_safety_ca.checks.reporting --config config/los_altos.yaml
```

A ranking built from police reports reads a fall in reports as a fall in
crashes. Departments change records systems, stop filing some kinds of report,
or file under another agency's code, and California's move from SWITRS to CCRS
is a time when this is likely. Run this check before comparing years or
cities.

It counts injury crashes and cyclist injury crashes per reporting agency and
year, and compares each year with the agency's own typical year (the median
of its years, leaving out the ones far from it). The `change` column says
what it found:

| `change` | The year's count is |
|---|---|
| `fall` | under 0.4 of the typical year |
| `rise` | over 2.5 times it |
| `possible fall`, `possible rise` | under 0.6 of it, or over 1.67 times: worth a look |

The other agencies are used only to excuse a move they share, so a
region-wide fall such as 2020 is not flagged, and a change in one agency is
never flagged against another. They excuse only part of a large move: the
agency's ratio is divided by the others' ratio, and that divisor is held
between 0.6 and 1.67. So a shared dip to about half is not flagged, and
agencies that collapse together still are. An agency needs a typical
year of at least 20 injury crashes (8 cyclist crashes) to be judged, and a
count that chance alone would rarely give. It also shows the share of each
agency's crashes found only in CCRS.

What the flags cannot tell you:

- With a single agency there is nothing to compare against (the `basis`
  column says "own history only"), and a real change in crashes looks the
  same as a change in reporting. Expect 2020 to be marked in such a city.
- An unfinished last year is judged against the part of the year up to the
  last crash date, and rises are not marked in it. If the records in fact run
  later than the last crash, reporting stopped early and the year is worse
  than it looks.
- A lasting step where no single year crosses the lines is not marked. The
  table of lasting changes below lists one when the new level is under 0.6
  of the old or over 1.67 times it; a smaller step (a department that settles
  at 0.65 of its old level, say) is in neither. A steady decline over many years is marked at one end or both,
  depending on where its median falls.
- No flag does not show that reporting was steady: a department can stop
  filing minor crashes while its total holds.

So read the yearly tables and the charts, not only the flags.

**Lasting changes of level** (`level_steps.csv`, also printed). The flags
judge one year at a time. This table looks for an agency whose yearly count
settles at a new level: under 0.6 of the old one or over 1.67 times it, with
at least three finished years on each side, at most one of them out of place,
and 20 crashes a year on the higher side. It looks in all injury crashes and
at each severity, and gives the first year of the new level and the typical
year before and after. For a step at one severity, `kind` says where the
crashes went:

| `kind` | Meaning |
|---|---|
| `regraded` | The agency's other severities changed the opposite way by a half to twice as much (`moved` is that share), so the crashes are probably still reported, at another severity |
| `fewer reports`, `more reports` | Nothing else took up the change |

In the 28 cities tried, 18 had at least one agency with a step, and the most
common was a fall in "complaint of pain" crashes, the least serious grade,
with no fall in the total large enough to flag. A ranking of all injury
crashes then compares years, and cities, that count minor crashes
differently. What to know about the table:

- It reports one step per agency and measure. A gap that opens and closes
  again may show as one of its two steps or not at all; the yearly flags are
  for that.
- The year can be one off where a change took two years to complete.
- `regraded` is only used for a severity that is a fifth or more of the
  agency's injury crashes; a rise in serious injuries beside a large fall in
  minor ones is listed as `more reports`.
- The unfinished last year is left out.
- Like a flag, a step is a question for the department. Crashes can really
  fall, and injuries can really get worse.

Two more pictures show what changed:

- **Reports per quarter by report format** (earlier format, CCRS format, in
  CCRS only). This shows when each agency moved to CCRS and whether its volume
  carried over. The format is inferred from the style of the TIMS case number,
  which TIMS does not document, so treat it as a strong hint and not as a
  record of when an agency changed systems. Numbers in no known style are
  shown as "not recognised". The quarter is the crash's, not the date the
  report was filed. It needs a TIMS export.
- **Injury crashes per year by severity.** A shift from one severity to
  another with a steady total points to a change in how injuries are graded,
  so counts by severity should not be compared across it.

Tables and one picture per measure, a small chart per agency, go to
`output/reporting/`.

A flag is a reason to ask the department, not proof that reporting changed.
Where an agency is flagged:

- do not read its later counts as a trend;
- expect a ranking pooled across cities to place its corners too high in later
  test years, because their past crashes still count but new ones are missing;
  score each city on its own instead, or leave the agency out of the test
  (this makes the test fairer; it does not put the missing crashes back);
- keep the flagged years out of any before-and-after comparison.

## Checking the ranking on a real city

With the crash tables and the street table built, the hold-out check finds the
intersections, places each crash at one, and scores every ranking on the
crashes after its cut-off year:

```bash
uv run python -m bike_safety_ca.checks.holdout --config config/los_altos.yaml
```

It scores the whole area and, separately, the config's own city. The output is
counts per ranking only.

The hold-out, corridor and ranking commands read the outlines and the street
table from `data/processed/` and the crash tables from
`data/processed/crashes/`. For a city built into a folder of its own, name
both:

```bash
uv run python -m bike_safety_ca.checks.holdout --config config/davis.yaml \
    --processed data/processed/davis --crashes data/processed/davis/crashes
```

Two things in the table guard against reading too much into few crashes:

- A window with fewer than 30 later crashes shows the count, as `too few
  (18)`, in place of a score, and the mean covers the scored windows only.
  This limits what the test can show, not what can be ranked: a city too small
  to be scored on its own is still covered by the score of the wider area it
  was fitted with.
- Children also get an `All-cyclist ranking` row: the ranking fitted to every
  cyclist crash, scored on later child crashes. Where there were too few child
  crashes to fit the model, a line under the table says to rank children by
  that row's ranking instead.

How a crash is placed matters, so the rules are worth knowing. A crash counts
at an intersection if it lies within 35 m of it, or if the report says it
happened at the intersection of two streets that meet there, within 100 m.
Nearness does not count when the report names two streets and neither meets
at that intersection: that is a freeway crash above a surface street, or a
wrong coordinate. Mapped corners within 25 m of each other are one
intersection, as are the two halves of a divided road's crossing; a few
chains of close corners therefore come out wide, and the intersection table's
`span_m` column says how wide.

```bash
uv run python -m bike_safety_ca.checks.sensitivity --config config/los_altos.yaml
```

runs the check again with one of these choices changed at a time (and, if you
give it other street tables, with streets of another date or a wider area)
and prints the scores side by side. Run it before relying on a ranking: a
result that moves a lot under these choices is not robust. A last table
builds the ranking with and without "complaint of pain" crashes, the least
serious grade, and scores both on later cyclist crashes (it also says in how
many windows each came from a fitted model and not the fallback): departments
differ in how many of those they file (see "Lasting changes of level"
above), and in the cities tried the ranking was slightly better with them
kept in. Scores depend on the area: the Los Altos figures in
`docs/forecasting_model.md` come from a smaller study area around Los Altos
schools, and the city-list outline gives somewhat lower ones. Street data is
© OpenStreetMap contributors, ODbL 1.0; credit them in anything you publish
from it.

A city's rank score depends on how evenly its risk is spread, so a low score
need not mean a poor ranking.

```bash
uv run python -m bike_safety_ca.checks.attainable --config config/berkeley.yaml \
    --crashes data/processed/berkeley/crashes --processed data/processed/berkeley
```

draws later crashes many times from the fitted model's own rates and scores
the ranking on each draw, window by window: the simulated mean is the score
to expect if the model were exactly right about the city, and the share of
draws below the real score says how unusual the real score is. It takes the
fitted parameters as known and skips windows where the model fell back to the
blend. `--synthetic` runs it on the made-up city. See "What the rank score
does and does not tell you" in `docs/where_the_ranking_helps.md`.

## The intersection ranking

```bash
uv run python -m bike_safety_ca.model --config config/los_altos.yaml
```

ranks every intersection in the area from all years of crashes, placed as the
hold-out check places them. It prints the method used and the number of
crashes the ranking was built from, and writes two files to `output/ranking/`
(`--out` names another folder): `intersection_ranking.csv` and
`intersection_ranking.geojson`, one row or point per intersection, highest
rank first.

| Column | Meaning |
|---|---|
| `rank` | 1 is the highest score |
| `intersection` | Its number among the intersections built from the street table |
| `streets` | Mapped names of the streets that meet there (the first three) |
| `street_keys` | Every street that meets there, under the short name used to match streets |
| `major`, `minor` | The class of the largest road there and of the next largest |
| `in_city` | Whether it lies inside the city limit; empty when there is no city-limit outline |
| `score` | What the rank follows |
| `expected_bike_crashes` | The model's estimate of the police-recorded bike crashes at the intersection over the whole of `first_year` to `last_year`, the same years as the two counts below. Not a count per year and not a forecast. Empty when the blend was used |
| `observed_bike_crashes`, `car_crashes` | Bike crashes and motor-vehicle-only crashes placed there |
| `method` | "street-length model" or "hand-built blend" |
| `spread_power` | The spread power the model was fitted with (1); empty for the blend |
| `fallback_reason` | Why the blend was used; empty for the model |
| `first_year`, `last_year` | The years of the crashes the ranking was built from, the same on every row. The last may be a part year |
| `longitude`, `latitude` | The intersection's point |

- `--top N` writes only the N highest-ranked intersections.
- `--children` builds the ranking from child cyclist crashes only and writes
  `intersection_ranking_children.csv` and `.geojson`. With fewer than 100
  child crashes at intersections it stops and says so, for the reason given
  under "Use it on your own counts"; `--force` builds it anyway, by the
  hand-built blend.
- `--processed`, `--crashes` and `--area` say where the built tables and the
  outline are, as for the hold-out check.

The ranking covers the whole area the crash tables cover; filter on `in_city`
for the city alone. The files give crash counts for single corners. Read
"Crash records" below before passing them on.

## Corridors

```bash
uv run python -m bike_safety_ca.checks.corridors --config config/los_altos.yaml --out output/corridors
```

ranks whole streets the same way. A corridor is every street with the same
name and street type once spellings are tidied ("FOOTHILL EXPY" and "Foothill
Expressway" are one; Park Avenue and Park Place are two). With a city limit,
each corridor is split into its part inside the city
and its part outside. Each crash counts in one place:

- at a corner, where the hold-out check placed it;
- otherwise between corners, on the street its report names first.

A corner counts fully for every street through it, so corridor totals add up
to more than the city's total. The forecast for a corridor is the sum of the
intersection model's expected counts at its corners, plus a model fitted to
street length and car crashes for the stretches between, each falling back to
past crashes when there are too few to fit. Expected counts are sums of
estimates that share street averages, so read them to the nearest few
crashes.

The check compares three rankings over the same windows: past crashes on the
corridor, street length alone, and the corridor model. It reports four
measures:

- the rank score;
- the rank correlation with later crashes, which still works when every
  corridor had a later crash;
- later crashes found in the top 10;
- the correlation of crashes per km with later crashes per km, for pieces at
  least 0.5 km long.

A window is scored only with 30 or more later crashes, each counted once.
The "training crashes" and "later crashes" columns are counted the same way,
so they are smaller than the sum of the corridor counts.

`--out` also writes forecast tables for the whole area and the city, for all
cyclists and for children. These are totals per street, with rates left empty
for pieces shorter than 0.5 km.

## The same checks over many cities

```bash
uv run python -m bike_safety_ca.checks.cities --configs config --pool 'pool_*' --out output/cities
```

runs three of the checks above for every config whose city has been built
under `data/processed/<config name>/` (its `crashes`, `network` and
`boundaries` folders): the hold-out, the lasting changes of level in police
reporting, and the ranking with and without "complaint of pain" crashes. It
prints the cross-city tables in `docs/where_the_ranking_helps.md` and, with
`--out`, writes the rows behind them, one per agency or per city and window.
It says which configs it left out and why.

Cities are compared as separate samples, so a config that overlaps others
must not be run as one more city. Name it with `--pool` if it is a pooled
area: it is then fitted as a whole and scored inside the limit of each city
that lies in it, beside that city's score when fitted alone. Otherwise leave
it out with `--skip`. Both take patterns on the config name.

## Crash summaries and the crash movement map

```bash
uv run python -m bike_safety_ca.report --config config/los_altos.yaml
```

`summary` prints and writes tables of totals for the whole area and for the
city: injury crashes by year and group, cyclist crashes by coded cause and by
time of day, and cyclists by age band. `map` writes
`output/crash_movement_map.html`, a single page that opens from disk. It draws
each cyclist crash with one arrow per party: the direction of travel the
officer recorded, turned to the nearest street, the movement before the crash,
and a colour for the kind of road user. Where no mapped street runs the
recorded way, the arrow keeps the bare compass direction and the pop-up says
so; a crash shown at a corner only because its report gave no direction is
marked too. At a corner, arrows turn to the streets that actually leave it,
so at a T or a bend each party comes along a real street. Reports do not give
lanes, so each road user is drawn keeping right on a street as wide as its
mapped lanes (a cyclist near the kerb, a motor vehicle turning right from the
right-hand lane, one turning left from the lane by the centre line) and the
crash where their paths first meet. A party is drawn on the other side where
its report says it was travelling the wrong way or in the opposing lane, or
where a cyclist's wrong-side riding is coded or suggested by the movements.
Coded means the cyclist's own movement is "travelling wrong way", or the cause
is wrong side of road and the cyclist is the party at fault. A wrong-side cause
with no cyclist at fault is shown as "wrong side cited, party unclear" and
counted on its own; no cyclist is drawn against traffic in such a crash, and it
is not counted as suggested by the movements either. A crash is in one of the
three counts at most. "Crossed into the opposing lane" is drawn across the
centre line and is not counted as wrong-side riding.
Where the movements as reported meet only with the cyclist on the other side
(against traffic, on the sidewalk or in the crosswalk), the cyclist is drawn
there with a dotted line and the pop-up says so; where they do not meet at
all, no meeting point is made up: each party is drawn beside the corner (the
dot shows the injury, not where they met) and the pop-up says the report may
have a direction or movement wrong. Turns leave along the real street on that
side. A driver entering traffic pulls out from the kerb, one parking pulls in
to it (a parking space or a driveway; the pop-up says the report does not say
which), and one changing lanes or merging moves over toward the kerb, so each
crosses the line of a cyclist riding along it. In a rear end, the arrow of the
party behind stops just short: behind a party stopped or slowing, or otherwise
the party at fault. The side panel counts the dotted and the not-meeting crashes. How each crash's movements fit is worked out once in Python
(`report.diagram.fit`) and stored on the crash as `fit`, so the map and any
table built from the crash rows agree. The page loads its map library from the internet when opened.

The map changes with zoom. Zoomed out, each intersection with cyclist crashes
is a circle sized by its count and coloured by its worst injury. In the
middle range each crash is a dot. Zoomed in to a corner, the crashes there
become a collision diagram: each crash shows the paths of the cyclist and the
other party up to where they met, with its injury and whether it was after
dark; crashes at about the same point fan out around it.
Crashes are placed at intersections by the same rules as the hold-out check.
The side panel lists the crashes in view and the repeated patterns among them,
such as a cyclist going straight and a car turning right the same way. Patterns
are relative, so the same conflict from any approach counts once; with one
intersection in view, each pattern also says which approaches it came from.
Clicking a pattern picks out its crashes. A "Streets in view" table groups the
crashes by street, however the reports spell it, with the counts of cyclists 18
or under and of fatal or serious injuries and the pattern and cause that repeat
most. "Print this view" prints what is on
screen on a landscape page, with the filters, the key, a scale bar, the data
credits and the panel's tables below the map.

With `--ranking output/ranking/intersection_ranking.csv` (from the
intersection ranking, below), the map gains a "Show" switch between recorded
crashes and predicted risk. The risk view draws a circle at each corner in
the city where the model's estimate is at least half a bike crash, sized by
the estimate, and lists the model's top corners (`--top`, 20 by default)
with what it saw at each; clicking a row finds the corner on the map. An
estimate is of the bike crashes recorded at the corner over all the years the
ranking was built from (the ranking file gives them as `first_year` and
`last_year`), beside the count on record for the same years. It is not a
count per year or a forecast of a later period. The
command also writes `top_corners.md`, a one-page list of them. With `--pdf` it
prints `top_corners.pdf` and `predicted_risk.pdf`, the risk view with its list
(this needs Google Chrome or Chromium). Opening the map with `?view=risk` after
its file name starts it on predicted risk, framed on those corners.

To print the same views every time, list them under `prints:` in the city's
config; `report map --pdf` prints each as `<name>.pdf`, with or without a
ranking:

```yaml
prints:
  - name: city                     # the map's opening view
  - {name: corner-1, at: North San Antonio Road / San Antonio Road / West El Camino Real, zoom: 18}
  - {name: downtown, centre: [37.776, -122.418], zoom: 14}
  - {name: risk-north, centre: [37.40, -122.11], zoom: 15, view: risk}
```

`at` is an intersection with at least one crash, named exactly as the map
names it (click its circle to see the name); the command stops, before
printing anything, if no intersection or more than one has that name. A
`centre` is latitude then longitude. `view: risk` prints the predicted-risk
view at that framing.
Add `--offline` to build the map library (Leaflet,
BSD licence, in `src/bike_safety_ca/report/vendor/`) into the page, so the
single file opens and works with no internet connection. The optional
OpenStreetMap tile background is the exception: it needs a connection and, as
its label on the page says, a web server, so serve the page over HTTP to use
it and do not expect it in a file opened from disk. "Print this view" in a browser,
or headless Chrome's `--print-to-pdf` with a view in the address's `#lat,lon,zoom`,
makes the PDFs to go with it.

The map shows individual crash records and carries the TIMS and CCRS
credits; it, its PDFs and the summary tables may be shared or published (see
"Crash records").

## Bicycle injuries treated in hospital

Police reports mostly cover crashes with cars. Hospital counts also catch the
falls and other injuries that police seldom see, and say how a county
compares with the rest of California once its residents' ages are allowed
for. The counts come from the California Department of Public Health's
[EpiCenter](https://skylab4.cdph.ca.gov/epicenter/): emergency department
visits and hospital admissions by county of residence, with no city, street
or crash location. Counts under 11 are hidden by the source.

> **You accept EpiCenter's user agreement yourself.** The downloader opens the
> site in a browser window and waits for you to read the agreement and click
> "I Agree"; it never clicks it for you, and stops if the agreement closes any
> other way. The agreement asks, among other things, that you credit
> CDPH/EpiCenter in anything you make from the counts, tell
> <EpiCenter@cdph.ca.gov> of publications, and never try to identify anyone.
> Once you have agreed, leave the window alone until the pull finishes.

```bash
# the county's tables, through a browser window (Playwright is not a dependency)
uv run --with playwright python -m bike_safety_ca.hospital.epicenter \
    --county "Santa Clara" --out data/raw/epicenter/santa_clara
# every California county's residents by year and age, from the Census Bureau
uv run python -m bike_safety_ca.hospital.population --out data/raw/census/pep
# the county report: visits by year and age, and the county against the state
uv run python -m bike_safety_ca.hospital.report --county "Santa Clara" \
    --tables data/raw/epicenter/santa_clara --residents data/raw/census/pep \
    --out output/hospital --pdf
# electric bicycles against other bicycles, all of California
uv run python -m bike_safety_ca.hospital.ebike \
    --tables data/raw/epicenter/santa_clara --residents data/raw/census/pep \
    --out output/hospital --pdf
```

Use one folder per county; the downloader refuses to mix two. `--pdf` needs
Google Chrome or Chromium. The pull drives the site one table at a time. By
default it pulls only the eight tables the two reports read; `--all` pulls the
full set (69 tables, much slower), and `--only` names tables to pull
again, such as `--only ed_total_age_groups`.

A hidden count is never worked out from totals or other cells. It enters
every calculation as "a whole number from 1 to 10", and the result is given
as a range. The one exception is a total stated as exact, such as the yearly
visits for children or adults: if any cell in it is hidden, the report stops
rather than count the blank as zero. Where printing a group's count would let a reader subtract their
way to a hidden one, the report leaves that group out
(`report.withheld`). `docs/county_rates_method.md` gives the method, including
how all 58 counties would be compared without taking a small county's figure
at face value. That comparison (`rates.fit_prior`) is written and tested on
made-up counties, but no command pulls every county's tables yet.

To see what a report looks like before pulling anything, `uv run python -m
bike_safety_ca.hospital.sample --out output/hospital_sample --pdf` runs the
report on made-up counts for an invented county (`docs/demo/hospital_sample.pdf`).

Every table and chart the reports print carries the credit: *Source:
California Department of Public Health, EpiCenter – California Injury Data
Online. Residents: U.S. Census Bureau, Population Estimates Program.*

## Crash records

This repository holds no crash, party or victim record tables, and its tests
use made-up data. Everything built from real records is written under `data/`
or `output/`, which git ignores. Get records from the sources rather than
from a copy, so they are current.

The two sources and their terms, as published in November 2026:

- **TIMS** ([terms of use](https://tims.berkeley.edu/about.php#terms)). The
  terms say nothing about passing data on or publishing results built from
  it. They ask that any published work or website using TIMS data credit it
  as: *Transportation Injury Mapping System (TIMS), Safe Transportation
  Research and Education Center, University of California, Berkeley.* They
  also say the data is provided as is and is not an official record, and
  that it may not be used in connection with pending litigation it relates
  to.
- **CCRS** ([data.ca.gov dataset `ccrs`](https://data.ca.gov/dataset/ccrs)),
  published by the California Highway Patrol. The portal labels it "Other
  (Public Domain)" with "No restrictions on public use" and asks for no
  credit. Crediting it as *California Crash Reporting System (CCRS),
  California Highway Patrol, via data.ca.gov* says where the figures came
  from.

Neither source's terms restricts publishing what is built from these
records: tables of totals, rank scores, the figures in `docs/`, and maps of
single crashes such as the crash map and its PDFs (TIMS maps single crashes
on its own site, and CCRS publishes record-level rows openly). Publish them
with both credits. The limits on how the data may be used, listed below,
still apply.

The original crash reports behind the rows are for the confidential use of
the CHP and the local authority that has jurisdiction (Vehicle Code §
20014); that covers the reports, not the published TIMS and CCRS rows. A map
of single crashes still shows real people's crashes, with month, place, age
band and injury, so think about the people in it before publishing a map of
a quiet street with a fatal or serious crash.

### Before you use this on real records

- **No data comes with the code.** You get crash records from TIMS or CCRS
  yourself, and their terms apply to you, not this repository's licence.
- **Record tables stay out of this repository.** The crash map, and
  anything else that draws single crashes, may be published with both
  credits; the record tables themselves are not committed here.
- **Not an official record.** TIMS and CCRS data are provided as is. Records
  are corrected and added after the fact, coordinates can be wrong, and
  police reporting changes over time (see the reporting check). Nothing here
  checks a crash against the original report.
- **Litigation.** TIMS's terms say that data from the site may not be used
  in connection with the pending litigation they describe; read them before
  using TIMS data near a lawsuit. Separately, data compiled or collected to
  plan federally funded highway safety improvements cannot be discovered or
  admitted as evidence in a damages action about a location it covers
  (23 U.S.C. 407, numbered 409 before 2021 and still cited that way on the
  TIMS site).
- **Not an engineering judgement.** A ranking, map or diagram points to
  places worth a closer look. Deciding what is wrong at a corner, and what to
  change, is for a qualified engineer who has looked at it. TIMS's terms tell
  Caltrans staff and those working for Caltrans not to rely on the site's
  data, or on anything made from it, for their decisions.
- **No warranty.** The code is offered under the MIT licence, with no warranty
  of any kind. This note summarises published terms as read in November 2026;
  it is not legal advice, and the sources' own terms govern.
