# Comparing counties on bicycle injuries treated in hospital

How `src/bike_safety_ca/hospital/` turns published county counts into a comparison that is
fair to small counties and honest about hidden counts. All figures are
published totals; no person is identified and no hidden count is recovered.

Source of the counts: California Department of Public Health, EpiCenter –
California Injury Data Online. Residents: U.S. Census Bureau, Population
Estimates Program.

## The question

Which counties have more, or fewer, bicycle injuries treated in hospital than
you would expect, and how sure can we be? The aim is practical: to help
cities and counties see where they stand and where to look harder.

## Three problems with the obvious answer

The obvious answer is visits divided by residents, sorted. It misleads in
three ways.

1. **Age.** Children aged 10–14 visit an emergency department for a bicycle
   injury about four times as often as people aged 65–84. A county with many
   children looks worse for that reason alone.
2. **Chance.** A county of 10,000 people with 4 visits one year and 9 the next
   has not doubled its risk. Sorted raw rates put the smallest counties at
   both ends of the list.
3. **Hidden counts.** The source does not publish a count from 1 to 10. Small
   counties, single years and narrow age groups are mostly hidden. Dropping
   those cells, or treating them as zero, biases every rate downward.

## Step 1: compare with what the county's ages predict

For each age group *a* take the statewide rate *s_a* (cases per resident per
year), from unique visits by age group. A county with *N_a* residents in that group would have

    E = Σ_a s_a · N_a

cases a year if it were exactly like the state. The county's **ratio** is its
cases divided by *E*: 1.3 means 30% more than its ages predict. This is
indirect standardisation; it needs the county's total and its residents by
age, but not the county's own counts by age, which are the cells most often
hidden. Residents come from the Census Bureau's yearly county estimates
(`bike_safety_ca.hospital.population`), so each year's cases are set against that year's
residents.

## Step 2: estimate every county's ratio together

Write *θ_c* for county *c*'s true ratio and *y* for a count in one of its
cells (say one year) with expected count *E*.

- **Counts scatter around their mean:** *y* ~ Poisson(*θ_c · E*).
- **Counties differ, but not without limit:** *θ_c* ~ Gamma with mean *m* and
  shape *k*, the same for all counties. A large *k* says counties are much
  alike; a small one says they differ widely.

The two numbers *m* and *k* are not chosen: they are fitted to all the
counties at once, by picking the values under which the observed cells are
most likely (`fit_prior`). So the data decide how much counties really differ
once chance is allowed for.

Given *m* and *k*, a county with total count *Y* and total expected *E* has

    estimated ratio = (k + Y) / (k/m + E)
                    = w · (Y/E) + (1 − w) · m,     w = E / (E + k/m)

a blend of the county's own ratio and the common mean. The weight *w* on the
county's own figure is close to 1 for a large county and small for a tiny
one. Nothing is tuned per county: the pull toward the mean is whatever the
county's amount of data implies. This is the same gamma–Poisson blend the
crash-history ranking uses for intersections
(`docs/forecasting_model.md`).

The whole distribution of *θ_c* is kept, not only its mean, which gives a 90%
range for each county and the chance that its ratio is above a chosen
reference (1 for the comparison with the state, step 4).

## Step 3: treat a hidden count as what it is

A hidden cell is not unknown: it is known to hold a whole number from 1 to
10. A cell with no row at all holds zero. So every cell is a pair (lowest,
highest): a published 37 is (37, 37), a hidden cell is (1, 10), an absent one
is (0, 0) (`cells`).

The model takes this in directly. Where a published cell contributes the
chance of exactly its count, a hidden cell contributes the chance of *any*
count from 1 to 10:

    P(1 ≤ y ≤ 10 | θ_c · E) = Σ_{n=1..10} Poisson(n | θ_c · E)

Everything else is unchanged. The consequences are the ones you would want:

- A hidden cell in a county that otherwise runs high is taken to be nearer
  10 than 1, and the reverse; the model weighs the ten values by how likely
  each is, given the county's other cells and its size.
- Hiding a count loses information, and the county's range reflects it: the
  result is the average over the ten possible counts, each weighted by how
  likely it is, not the answer for any one of them.
- The fitted spread *k* uses the hidden cells too, so small counties are not
  left out of the estimate of how much counties differ.

With hidden cells the tidy formula of step 2 no longer applies, so the
calculation is done numerically, on a grid in the logarithm of the ratio
(`posterior`). A county with nothing hidden uses the formula directly, and
the grid is tested against the formula, including at zero counts and at very
small and very large expected counts.

### What is never done

- **No subtraction.** A hidden count is never worked out from a total and the
  other cells. `cells` reads each cell's own row and nothing else, and no
  function takes a total as an input. A test builds a table where
  subtraction would give the hidden count exactly and checks the cell stays
  1 to 10.
- **No fill-in.** No single number (5.5, the midpoint, a model's guess) is
  ever substituted for a hidden cell and then treated as data.
- **Care about giving it away in print.** A table can reveal a hidden count
  without stating it: a reader who knows the total subtracts every printed
  count. So wherever a cell is hidden the report leaves out one published
  count as well (`bike_safety_ca.hospital.report.withheld`): the group that joins a
  published cell and a hidden one, or failing that the next age group. The
  choice depends only on which cells are hidden, never on the size of a
  count, because a rule that tested the counts would tell the reader the
  result of the test. This is a precaution, not a guarantee. If the count
  left out is itself close to 11 the remainder still narrows the hidden one,
  and a reader can combine a report with tables the source publishes. What
  does hold is that a report prints nothing the source's own table does not
  show. Whether more is needed is a question put to CDPH.

### Why not the simpler ways

- *Drop hidden cells:* removes exactly the low counts, so small counties'
  rates are biased down and their uncertainty is understated.
- *Pool until nothing is hidden:* honest, and still the right thing for a
  table meant to be read; but it throws away the year-by-year detail of every
  larger county to accommodate the smallest.
- *Substitute 5.5:* gives one answer where the truth is a range, and is too
  high for the smallest counties, whose hidden cells are mostly 1s and 2s.

## Step 4: calling a county higher or lower

A county is called **higher** (or **lower**) than the state only when the
chance that its true ratio is above (below) 1, the statewide rate for its
ages, is at least 95%. Otherwise no call is made. The comparison is with 1,
not with the fitted mean *m*: *m* is the centre of the counties, each
counted once, and need not equal the statewide figure, which is dominated by
the largest counties. A report shows, for each county: cases expected, the raw ratio
(a range if anything is hidden), the estimated ratio, its 90% range and the
call.

## How it was checked

On made-up states of 58 counties whose true ratios are known, with sizes from
under one expected case a year to hundreds and about six cells in ten hidden
(`tests/test_hospital_rates.py`):

- the estimates are closer to the truth than raw ratios (mean squared error
  under 70% of the raw figure's);
- the 90% ranges contain the truth between 84% and 96% of the time;
- fewer than 5% of "higher"/"lower" calls (against a true ratio of 1) are
  wrong;
- the fitted spread is near the true one with and without hidden cells
  (taken over several made-up states: in any single one, hiding six cells in
  ten leaves the spread known only roughly);
- with nothing hidden the results equal the closed-form answers;
- counties made to differ by chance alone are fitted as "all alike".

These checks use one kind of made-up state (true spread *k* = 6). They show
the method works as designed there; they are not evidence about real
counties.

## Limits

- **Per resident, not per ride.** A county where more people cycle has more
  injuries per resident. A high ratio is a reason to look, not a verdict.
- **Visits, not people.** The counts are hospital encounters; one person can
  have several.
- **Where people live, not where they crashed.** Counts are by county of
  residence.
- **Coding.** Hospitals differ in how fully they code causes; some of the
  difference between counties is recording.
- **Statewide rates count each visit once.** EpiCenter counts a visit once
  under each injury mechanism or cause it is coded with, so a table split by
  cause adds up to more than the visits (its FAQ; CDPH confirmed this in
  reply to us in November 2026). The statewide rates therefore come from the
  statewide table of unique visits by age group, not from the cause rows.
  The e-bike report, which has to split by cause, says so and prints the
  cause rows' total beside the unique visits.
- **The state's own figures are taken as exact** apart from their hidden
  cells: chance in the statewide counts is not carried into the ranges.
- **The spread is itself an estimate.** *m* and *k* are fitted and then used
  as if known, so ranges are slightly too narrow, most of all when many cells
  are hidden.
- **One ratio per county.** A county is given one ratio for all years and
  ages in the fit. A county whose rate is changing fast needs a fit by
  period.
- **Not yet run on real counties.** Only two counties' tables and the
  statewide tables are on hand. The 58-county fit waits on the data.
