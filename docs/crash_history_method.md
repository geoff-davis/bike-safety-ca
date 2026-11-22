# Ranking intersections from crash history alone: the model and the argument for it

Status: working note, 16 November 2026. Numbers are preliminary. All figures are
totals over intersections; no individual crash is described.

This note gives the argument behind the crash-only ranking in
`src/bike_safety_ca/model/crash_history.py` (`fit_street_model`) and records the tests of
it. The ranking uses no modelled traffic. Its inputs are police-reported bike
and car crashes at each intersection, the same along the named streets that
meet there, and the number of intersections on each named street.

**What a reader can and cannot rerun.** The figures come from the Los Altos
study-area analysis, which uses police crash records that are not in this
repository. Two more things are not here. One is that analysis's own ranking,
built from road features and modelled bike traffic and called the
"road-and-traffic model" below: neither it nor its modelled school bike trips
are included, so its rows cannot be rerun. The other is the one-off scripts
behind every table except the first one under "Rank score", which comes from
this repository's hold-out command. See "Which figures are current" and
"Reproducing".

## Summary

- The model follows from two ordinary assumptions: crash counts are Poisson
  with rates that vary from corner to corner, and the bike-crash rate is a
  product of powers of car and bike traffic.
- Neither traffic flow is measured. The corner's car-crash record stands in for
  car traffic, and the bike-crash record of the corner's streets stands in for
  bike traffic.
- Three choices matter, and each was made on the fitting years alone:
  1. a street with little record is pulled toward what is typical for a street
     with that many intersections, and pulled hard;
  2. a corner's own crash counts for more where little is expected;
  3. a corner on two streets adds their averages.
- On later crashes the model ranks as well as the Los Altos analysis's
  road-and-traffic model, which uses road features and modelled bike
  traffic, and better than the earlier
  crash-only formulas (table below). These are retrospective tests: the later
  years were seen while the model was being built, about 100 variants were
  tried on the same windows, and the windows overlap. They show the model is
  reasonable. Every window also uses the street map of 2026, so they ask how
  the ranking does on today's intersections, not what a ranking made in 2018
  could have known. They are not an independent measure of how well it will do on
  new years or another city, which needs a test on data not yet looked at.
- What is ranked is the expected number of police-recorded bike crashes. It is
  not risk per rider: a corner can rank high because many people cycle
  through it.
- Road class and measured car volumes add nothing clear. Modelled school bike
  traffic helps the child ranking across the study area but not clearly in Los
  Altos.
- Once its level is set to the actual total, its forecast of how crashes
  spread across groups of intersections, and the overall size of its stated
  spread, match what happened before 2023. That is a check on totals over
  many intersections, not on the uncertainty stated for any one of them. No
  model forecasts the overall level: recorded crashes per year fell after the
  fitting years.

## The argument

### 1. Counts are Poisson, and rates vary from corner to corner

Let $y_i$ be the bike crashes recorded at intersection $i$ over the fitting
years, with underlying rate $\lambda_i$:

$$y_i \mid \lambda_i \sim \text{Poisson}(\lambda_i).$$

Let $\mu_i$ be what the surroundings lead us to expect at the corner (steps 3
to 5). Corners with the same $\mu$ do not share one rate. Take the rates as
gamma-distributed around $\mu_i$ with shape $s_i$:

$$\lambda_i \sim \text{Gamma}(\text{shape } s_i,\ \text{mean } \mu_i).$$

The counts are then negative binomial with variance $\mu_i + \mu_i^2/s_i$. This
is the standard model for crash counts.

### 2. The best estimate blends the corner's count with the expectation

Given the count, the expected rate is

$$E[\lambda_i \mid y_i] \;=\; \frac{s_i + y_i}{s_i/\mu_i + 1}
\;=\; w_i\,\mu_i + (1 - w_i)\,y_i, \qquad w_i = \frac{s_i}{s_i + \mu_i}.$$

This is the empirical Bayes estimate used throughout road safety work to
correct regression to the mean. If rates did not vary (a plain Poisson,
$s \to \infty$), the corner's own count would carry no information.

How much the own count should weigh depends on how the spread of rates grows
with the expectation. Write the variance as $\mu + \alpha\,\mu^{p}$, so that
$s_i = \mu_i^{2-p}/\alpha$:

- $p = 2$ is the textbook case, with one shape for every corner. One crash then
  multiplies the estimate by $1 + 1/s$, which leaves a corner with a low
  expectation low.
- $p = 1$ gives $E[\lambda \mid y] = (\mu + \alpha y)/(1 + \alpha)$: every
  corner's own count gets the same weight, $\alpha/(1+\alpha)$.

The fitting years give $p$ between 1.2 and 1.6, and $p = 2$ fits them clearly
worse. That is a comparison of fits on the fitting years, not a formal test:
the counts at corners on one street are not independent. In words: the
less the surroundings tell us about a corner, the more its own record should
count. `fit_street_model` fits $p$.

### 3. The expectation is a product of powers

Suppose the bike-crash rate depends on car flow $V$ and bike flow $B$ as

$$\lambda^{\text{bike}} = c\,V^{a} B^{b},$$

the usual form for intersection crash models, and car crashes depend on car
flow as $\lambda^{\text{car}} \propto V^{q}$. Then:

- car flow can be replaced by the corner's car-crash rate:
  $V^{a} \propto (\lambda^{\text{car}})^{a/q}$;
- bike flow is similar along a street, because riders travel along it, so the
  street's bike-crash record stands in for $B^{b}$.

The model is therefore

$$\mu_i = c\,\bigl(m_i^{\text{bike}}\bigr)^{b}\,
\bigl(E[\lambda_i^{\text{car}} \mid y_i^{\text{car}}]\bigr)^{a},$$

with $m_i^{\text{bike}}$ the street bike average of step 4 and the car term the
blend of step 2 applied to the corner's car count and its street's car average.
The two terms are built differently: the bike term leaves the corner's own
count out, and the car term includes it. "The three blends, side by side"
below sets out the differences and the reasons.

### 4. The street average, and what a street with no record is worth

For each named street, the average at corner $i$ is taken over the street's
other corners, so that a corner's own count is not on both sides of the fit.
The exclusion is of the corner's own count from its neighbours' average only:
the typical-value curve $t(n)$ is fitted once on all streets, the corner's
included, so a trace of its count remains through that curve.
The median named street has two intersections, so most street averages rest on
very little and must be pulled toward a typical value. Two points decide how.

**What is typical depends on the street's length.** Bike crashes per corner
rise with the number of intersections $n$ on the street, roughly as $n^{0.7}$
(children: $n^{0.6}$; car crashes: $n^{0.84}$). Long named streets are the
through routes. The typical value $t(n)$ is fitted to the street totals by
Poisson regression. Pulling a short street with no record toward the overall
mean, as the first version of this model did, rates it too high.

**The pull is strong.** The street average is

$$\bar m = \frac{\text{crashes at the street's other corners} + Q\,t(n)}{(n - 1) + Q},$$

a street's own record weighed against $Q$ imaginary corners at the typical
value. The fitting years favour $Q \approx 20$ in every window, for all
cyclists and for children. A street's own record therefore counts for much only
on long streets.

### 5. A corner on two streets adds their averages

Riders arrive along both streets, so $m_i^{\text{bike}}$ is the sum of the
averages of the corner's streets, not their mean. The sum fits the fitting
years better (AIC lower by about 30 to 50; AIC is used here only to compare
fits, since the likelihood treats corners on one street as independent).

## The three blends, side by side

The model pulls a noisy number toward a steadier one in three places. They are
not the same operation, and the differences are deliberate.

| | A. Street bike average | B. Corner's car crashes | C. Corner's bike crashes |
|---|---|---|---|
| What is noisy | The average bike crashes at the street's other corners | The corner's own car count | The corner's own bike count |
| Pulled toward | The typical value for a street with that many intersections, $t(n)$ | The street's car average (itself pulled toward $t^{\text{car}}(n)$) | The fitted expectation $\mu_i$ |
| Is the corner's own count in it? | No | Yes | Yes |
| Strength | $Q = 20$ imaginary corners | Street average: $Q = 1$. Blend: one gamma shape, about 0.25 | Shape $\mu_i^{2-p}/\alpha$, with $p$ fitted (1.2 to 1.6) |
| Where in the model | A predictor of $\mu_i$ (step 4) | A predictor of $\mu_i$ (step 3) | The last step, giving the estimate to rank by (step 2) |
| Code | `street_length_average(bike, pull)` | `street_length_average(car, car_pull)`, `fit_shape`, `gamma_blend` | `gamma_blend` with `prior_shape` |

**Why the corner's own bike count is kept out of A.** Bike crashes are what the
model fits. If a corner's own bike crashes were inside a predictor, the same
number would be on both sides of the fit. So A uses the neighbours only, and
the corner's own bike record enters directly only in C. Two indirect routes
remain: the typical-value curve is fitted on all streets, and each corner's
count is in its neighbours' averages, whose counts are in its own. The fit
therefore treats as independent some counts that are not, and its likelihood
is a fitting criterion, not grounds for standard errors or model-selection
statistics. Car crashes are only a
predictor, so the corner's own car count can go straight into B.

**Why A is pulled hard and B's street average is not.** Both strengths were
compared on the fitting years.

- For bike crashes the fit improves steadily up to about 20 imaginary corners
  in every window (training log-likelihood for all cyclists to 2022: −1454 at
  $Q = 1$, −1428 at 8, −1422 at 20, −1428 at 40). Bike crashes are sparse, so a
  street's own average is mostly noise unless the street is long.
- For car crashes the strength hardly matters: going from 1 to 3 or 8
  imaginary corners changes the training log-likelihood by about 1, in either
  direction. It is left at 1.

The car pull matters little because the street's car average plays a small
part in B. With a shape of about 0.25, the corner's own car count gets more
than half the weight wherever the street average is above 0.25 crashes. The
street average mainly settles what a corner with no car crash gets in place of
zero.

**Why C has a fitted spread power and B does not.** In C the power $p$ decides
how much one bike crash moves a corner with a low expectation, and the fitting
years fit clearly worse with the textbook value of 2 (step 2). In B the textbook form is used
with one fitted shape. A fitted power for the car blend has not been tried;
given how little the car pull matters, it is unlikely to change much.

**What each blend does to a corner with no record.** A gives a corner on a
street with no bike crash the typical value for a street of that length, which
is low for short streets. B gives a corner with no car crash a small positive
car term set by its street. C leaves a corner with no bike crash a little
below its expectation: $\mu_i\,s_i/(s_i + \mu_i)$.

## How the earlier formulas relate to it

Two earlier rankings are still in the code. The model explains why they worked.

The hand-built score, `street_blend_score`, is

$$\Bigl(1 + \tfrac{y^{\text{bike}} + m^{\text{bike}}}{2}\Bigr)
\Bigl(1 + \tfrac{y^{\text{car}} + 0.5\,m^{\text{car}}}{1.5}\Bigr).$$

- The product is step 3.
- The fixed-weight blend of a corner with its street is step 2 with $p = 1$.
- The "1 +" keeps a corner with no record from scoring zero, the job the pull
  does in step 4.

The earlier fitted formula, `fit_history_model`, is a negative binomial fit on
$(1 + \text{car})$, $(1 + \text{street bike sum})$ and
$(1 + \text{street car sum})$, with fitted powers of about 0.8, 1.9 and 0.5 to
1.0. "Street sum" here is what `same_street_mean` returns: for each street the
corner is on, the mean count at the street's other corners, added over the
corner's streets. It is a sum over streets of per-street means, not a total
of crashes along the street.

- Raw street sums with "1 +" never lift a street with no record to the average,
  so short streets are treated as quiet.
- The power of 1.9 trusts a street's record mainly where it is large, which
  means long streets. That imitates the strong pull.
- The street car sum stands in for the street's importance, the part street
  length plays in the model.
- The "1 +" floors compress the low end, so a corner's own crash counts for
  more on quiet streets, as $p < 2$ does.

Before the street-length change the fitted formula's whole advantage lay among
quiet corners: taking the derived model's top 800 and ordering the rest by the
fitted formula reproduced the fitted formula's rank score (0.837 against 0.836).

## Tests

These are retrospective tests on years seen during development (see Summary).
The second window lies inside the first, so the three are not independent.

Each ranking was built from crashes up to a cut-off year and scored on bike
crashes after it, in three windows: fit 2014–2018 and test 2019–2022; fit
2014–2020 and test 2021–2022; fit 2014–2022 and test 2023 on. The rank score is
the chance that an intersection with a later crash is ranked above one without
(0.5 is a coin toss).

The study area has 4,208 intersections and Los Altos 803. Later bike crashes in
the three windows: 261, 114 and 218 across the study area (87, 40 and 76
involving a cyclist aged 18 or under); 45, 22 and 32 in Los Altos (18, 9 and 18).

The Los Altos columns in this section rest on few later crashes: 22 in the
middle window for all cyclists and 18, 9 and 18 for children. The hold-out
command now leaves a window with fewer than 30 unscored, so it no longer
prints a child score for Los Altos, and its all-cyclist mean for Los Altos
covers two windows (0.845). The Los Altos figures below were computed before
that floor and are kept as the record of how the model was chosen. Read them
as indications only. The study-area columns are the test; Los Altos
intersections are part of it.

**Which figures are current.** The table just below, and the counts above, are
from the repository's hold-out command on the crash tables of 16 November
2026, after the fixes of 15 and 16 November (cyclists of unrecorded age
counted, stricter linking of TIMS and CCRS reports, and a crash no longer
placed at an intersection when its report names two other streets, but at
the next nearest one within 35 m that it could describe). Its study-area
columns, and the study-area rows of the table by window, were rerun on the
crash tables of 21 November 2026, after further fixes to street names and to
the merge of the two sources; the Los Altos columns were not. Every
other table in this note is from earlier one-off runs, whose scripts are not
included, and has not been rerun.
Those fixes moved the street-length model's mean scores by 0.002 at most,
except in Los Altos for all cyclists (0.847 before, 0.855 now), so read the
older tables' model rows with that in mind. The road-and-traffic model's row
was not rerun: it uses its own crash placement.

### Rank score

Average over the three windows

| Ranking | Study area, all cyclists | Study area, children | Los Altos, all cyclists | Los Altos, children |
|---|---|---|---|---|
| Past bike crashes | 0.701 | 0.604 | 0.686 | 0.557 |
| Bike + car crashes, added | 0.780 | 0.760 | 0.767 | 0.711 |
| Bike x car crashes, blended with street averages (`street_blend_score`) | 0.832 | 0.833 | 0.841 | 0.804 |
| Crash history with same-street averages (`fit_history_model`) | 0.838 | 0.838 | 0.837 | 0.815 |
| Street-length model (`fit_street_model`) | 0.858 | 0.854 | 0.855 | 0.847 |
| Road-and-traffic model, refitted (not rerun) | 0.856 | 0.866 | 0.830 | 0.808 |

The first five names are the labels the hold-out command prints. In the text
of this note "Bike x car crashes, blended with street averages" is the
hand-built score, and "Crash history with same-street averages" is the earlier
fitted formula.

By window, street-length model then road-and-traffic model:

| | 2019–2022 | 2021–2022 | 2023 on |
|---|---|---|---|
| Study area, all cyclists | 0.850, 0.864 | 0.837, 0.832 | 0.886, 0.871 |
| Study area, children | 0.861, 0.881 | 0.859, 0.859 | 0.843, 0.857 |
| Los Altos, all cyclists | 0.862, 0.854 | 0.874, 0.853 | 0.830, 0.783 |
| Los Altos, children | 0.854, 0.825 | 0.905, 0.848 | 0.782, 0.752 |

(The first figure of each pair is the street-length model's: current in the
study-area rows, from the earlier run in the Los Altos rows. The second, the
road-and-traffic model's, was not rerun.)

Resampling intersections (300 draws; 5% to 95% range of the difference in
average rank score):

| Street-length model minus | Study area, all | Study area, children | Los Altos, all | Los Altos, children |
|---|---|---|---|---|
| Crash history with same-street averages | +0.020 (0.015 to 0.026) | +0.017 (0.007 to 0.024) | +0.018 (0.010 to 0.027) | +0.034 (0.016 to 0.051) |
| Road-and-traffic model | 0.000 (−0.011 to 0.011) | −0.013 (−0.026 to 0.001) | +0.017 (−0.002 to 0.037) | +0.038 (0.002 to 0.081) |

### Later crashes at the highest-ranked intersections

Summed over the three windows (the windows overlap, so the sums are for
comparison only); top 25 / top 50 / top 100:

| Ranking | Study area, all (of 586) | Study area, children (of 204) | Los Altos, all (of 101) | Los Altos, children (of 45) |
|---|---|---|---|---|
| Past bike crashes | 50 / 84 / 140 | 15 / 22 / 33 | 21 / 33 / 46 | 6 / 9 / 11 |
| Bike x car crashes, blended with street averages | 64 / 107 / 158 | 20 / 26 / 41 | 26 / 35 / 57 | 5 / 10 / 23 |
| Crash history with same-street averages | 65 / 104 / 162 | 23 / 30 / 42 | 23 / 38 / 61 | 4 / 13 / 18 |
| Street-length model | 64 / 104 / 172 | 21 / 33 / 41 | 22 / 41 / 59 | 7 / 11 / 27 |
| Road-and-traffic model, refitted | 60 / 105 / 159 | 21 / 35 / 44 | 24 / 39 / 56 | 6 / 8 / 16 |

At the very top of the list the fitted rankings are level within noise. The
street-length model's gain is further down, mostly in ordering the corners with
no bike or car crash of their own. Those are about 3,400 of the 4,208
intersections and have 22% to 35% of later crashes. Rank score among them:
0.66 for the first version of the model, 0.69 for the earlier fitted formula,
0.75 for the street-length model.

### What each choice contributes

Average rank score, and the forecast log-likelihood summed over windows with
the level set to the actual total (higher is better). One-off runs, not
included.

| Version | Study area, all | Los Altos, all | Log-likelihood, study area, all |
|---|---|---|---|
| First version: mean over streets, pulled to the overall mean, $p = 2$ | 0.817 | 0.796 | −1880 |
| Sum over streets | 0.824 | 0.792 | −1861 |
| and $p$ fitted | 0.827 | 0.810 | −1845 |
| and pulled to the street-length value, $Q = 20$ (the model) | 0.856 | 0.847 | −1792 |
| Street length alone, no street bike record | 0.849 | 0.842 | −1825 |
| Crash history with same-street averages | 0.836 | 0.828 | −1850 |

Fitting $p$ matters most in Los Altos after 2022, where the first version
scored 0.73 and the version with $p$ fitted 0.80.

### Fitted values

| Fitted on | Street bike power | Car power | $p$ | $\alpha$ | Car shape |
|---|---|---|---|---|---|
| All cyclists, 2014–2018 | 1.45 | 0.39 | 1.24 | 0.33 | 0.26 |
| All cyclists, 2014–2020 | 1.59 | 0.34 | 1.34 | 0.43 | 0.25 |
| All cyclists, 2014–2022 | 1.52 | 0.36 | 1.39 | 0.44 | 0.24 |
| Children, 2014–2018 | 1.39 | 0.39 | 1.59 | 0.48 | 0.26 |
| Children, 2014–2020 | 1.52 | 0.36 | 1.52 | 0.55 | 0.25 |
| Children, 2014–2022 | 1.49 | 0.36 | 1.49 | 0.49 | 0.24 |

The values are stable between fits. The street bike power is above 1 because
the strong pull narrows the range of the street averages; the power widens it
again. It is not an estimate of how crashes grow with bike traffic.

### Forecast means and variances

After the fit, each corner's rate has a gamma distribution with shape
$s_i + y_i$ and rate $s_i/\mu_i + 1$. The count in a later period $r$ times as
long is negative binomial with

$$\text{mean} = r\,\frac{s_i + y_i}{s_i/\mu_i + 1}, \qquad
\text{variance} = \text{mean} + r^2\,\frac{s_i + y_i}{(s_i/\mu_i + 1)^2}.$$

`forecast` returns both. The checks below used the two windows before 2023.

**Level.** Carried forward at the fitting years' rate, the forecast is too high:
358 against 263 actual for all cyclists in 2019–2022, and 170 against 116 in
2021–2022 (children: 139 against 87, and 63 against 40). Recorded crashes per
year fell; a model of where crashes happen cannot know that. In Los Altos the
figures are 58 against 46, and 28 against 23.

**Spread.** With the level set to the actual total, intersections grouped by
forecast rank, study area; forecast ± one standard deviation, then actual:

| Rank band | All cyclists, 2019–22 | All cyclists, 2021–22 | Children, 2019–22 | Children, 2021–22 |
|---|---|---|---|---|
| Top 25 | 33 ± 6, 26 | 14 ± 4, 17 | 10 ± 3, 10 | 5 ± 2, 5 |
| 26–100 | 49 ± 8, 46 | 22 ± 5, 15 | 15 ± 4, 8 | 7 ± 3, 3 |
| 101–400 | 80 ± 10, 79 | 36 ± 6, 36 | 24 ± 5, 31 | 12 ± 3, 10 |
| The other 3,808 | 100 ± 10, 112 | 44 ± 7, 48 | 39 ± 6, 38 | 17 ± 4, 22 |

**Variance.** Summed squared forecast errors divided by summed forecast variance
are 0.93 to 1.03 (1 means the stated uncertainty is right). Both spread checks
are made after setting the forecast's level to the actual total, so they test
how the forecast shares crashes out among intersections, not whether it gets
the total right, which it does not (see Level). The variances also take the
fitted street averages and parameters as known. So these checks show the
spread is of the right size overall; they do not show that the stated
uncertainty for any one intersection is calibrated. For all cyclists in
2019–2022 the model expected 210 intersections with at least one later crash
and 39 with two or more; 217 and 40 had them.

## Adding road and traffic information

Three kinds of extra information were tried on top of the model. Each was
judged first on the fitting years and then on later crashes. Figures are the
average rank score over the three windows. One-off runs, not included.

### Road class

Each named street was given a class (local, collector, arterial, major
arterial) inferred from the classes recorded at its intersections. The label
is approximate for short streets.

| Version | Study area, all | Study area, children | Los Altos, all | Los Altos, children |
|---|---|---|---|---|
| The model: streets pulled toward the typical value for their length | 0.856 | 0.853 | 0.847 | 0.847 |
| Pulled toward the typical value for their class | 0.842 | 0.834 | 0.815 | 0.806 |
| Pulled toward the typical value for class and length | 0.852 | 0.847 | 0.833 | 0.828 |
| The model, plus the corner's major and minor road class as factors | 0.860 | 0.857 | 0.846 | 0.848 |

- Class is a worse target than length, and adding class to length is worse
  than length alone, on the fitting years as well as the later ones.
- Looked at alone, class explains street crash totals better than length does.
  It stops helping once the corner's car record is in the model: car crashes
  already carry what class knows. Length adds something else, whether the
  street is a through route.
- Class as five extra corner factors improves the training fit a little (AIC
  lower by 5 to 13 for all cyclists, about level for children). The gain on
  later crashes is within noise.

### Measured car volumes

Daily car volumes are available for 70 named streets (federal highway
monitoring data and municipal counts), which touch 1,183 of the 4,208
intersections. The bicycle count inventory consulted has no location inside
the study area.

- **As a check on the argument.** On counted streets with three or more
  intersections, measured volume has a rank correlation of 0.72 with car
  crashes per corner and 0.59 with bike crashes per corner. The crash record is
  a fair stand-in for traffic (step 3).
- **As part of the value a street is pulled toward.** Worse: 0.850 against
  0.856 in the study area and 0.841 against 0.847 in Los Altos, all cyclists.
- **As a separate corner factor.** No real change: the rank score moves by
  0.003 or less in either direction.
- The fitted power on volume is about −0.3. Given the same crash record, a
  corner on a busier street has slightly fewer bike crashes.

### Modelled bike traffic

Modelled school bike trips through each corner, from the Los Altos analysis's
route model (the quantity the road-and-traffic model uses; not included here),
were added as one more factor,
$(1 + \text{school bike trips})^{g}$.

| Version | Study area, all | Study area, children | Los Altos, all | Los Altos, children |
|---|---|---|---|---|
| The model | 0.856 | 0.853 | 0.847 | 0.847 |
| Plus modelled bicycles to school | 0.857 | 0.866 | 0.851 | 0.852 |
| Plus modelled general bicycles | 0.857 | 0.859 | 0.852 | 0.852 |
| Plus all five modelled traffic terms | 0.860 | 0.868 | 0.850 | 0.833 |
| Road-and-traffic model, refitted | 0.856 | 0.866 | 0.830 | 0.808 |

- For children across the study area the one term closes the gap to the
  road-and-traffic model. The range from resampling intersections is +0.003 to
  +0.024, and the training fit improves (AIC lower by 30 to 43). The
  resampling treats intersections as independent and does not redo the
  choice of model, so the range is narrower than the real uncertainty.
- For children in Los Altos the change is within noise (−0.017 to +0.028).
  For all cyclists the ranking does not change.
- The fitted power $g$ is about 0.35 for children: doubling modelled riders
  raises expected child crashes by about 27%. The street bike power falls from
  1.49 to 1.29, so the two terms partly overlap.
- All five modelled terms together overfit for children in Los Altos.
- In the Los Altos child list fitted on all years, 18 of the top 25 corners
  are the same with and without the term. Corners that drop are mostly ones
  with no child crash on record and almost no modelled school riders; corners
  that rise mostly have many modelled riders and also no child crash on
  record.

The term is not in `fit_street_model`. The crash-only model stays the main
ranking; modelled school riders are a second view for children.

## Tried and dropped

- **Older crashes counting for less.** An old crash predicts later ones about
  as well as a recent one; no consistent difference across windows.
- **The street's car record as an extra factor.** Fitted power near zero.
- **Street bike crashes per car crash, not per corner.** Fits much worse.
- **Pulling street averages toward a value predicted from the street's car
  record.** No gain.
- **Street length as a separate factor beside the street average.** No better
  than the pull, with one more parameter.
- **Dividing the corner's car count by its street's car average,** which the
  theory suggests if bike flow were constant along a street. Worse.
- **No-fit versions of the product with a fixed shape.** They rank about as
  well as the hand-built score (0.82 to 0.83) but are far too concentrated to
  be read as expected counts.

## How this relates to the code

- `fit_street_model` is the model, built from `street_length_average`,
  `gamma_blend` and `fit_shape`. `forecast` gives the mean and variance of later
  counts. The pull ($Q = 20$, and 1 for the car average) is an argument, not
  fitted; the spread power $p$ is fitted unless given.
- `street_blend_score` is the hand-built score. It needs no fitting and gives a
  ranking only, not an expected count.
- `fit_history_model` is the earlier fitted formula, kept for comparison.

## Limits

- About 100 variants have now been scored on the same three windows, and two of
  the windows overlap. Differences of 0.01 are within noise. The model's
  choices were made on the fitting years, and the later years agree, but the
  later years were seen along the way.
- The model has about ten fitted numbers, against none for the hand-built
  score.
- The car blend uses the textbook spread (one shape for every corner); a fitted
  spread power was tried only for bike crashes.
- Street length is counted in study-area intersections, and same-named streets
  in different cities are treated as one street.
- Street length alone does most of the work of the street term (0.849 against
  0.856). The street's own bike record adds a little, mainly on long streets.
- For children across the study area the road-and-traffic model is still
  slightly ahead (0.866 against 0.853).
- Recorded crashes per year fell after 2022, when police reporting appears to
  have changed. That affects the level of any forecast and may affect rankings
  in the last window.
- A change in one department's reporting distorts a ranking pooled across
  cities: its corners keep their past crashes but record few new ones, so they
  sit above corners elsewhere that go on to have crashes. In the Los Altos case
  study, widening the area to whole neighbouring cities lowered the rank score
  for 2023 onwards from 0.89 to 0.84 for all cyclists, while the score inside
  the original area was unchanged (0.88) and each city scored on its own stayed
  between 0.82 and 0.90. Run `python -m bike_safety_ca.checks.reporting` before
  comparing years or cities, particularly around the move from SWITRS to CCRS,
  and rank within a city where an agency is flagged.
- Fatal and severe crashes are too few to test separately.

## References

Checked on 16 November 2026. The four papers were checked against the
publisher's or an archive's record, and Greene's variance form against the
paper itself. The two books were checked for their details and subject only:
the text of neither was read for this note.

- Hauer, E. (1997). *Observational Before–After Studies in Road Safety:
  Estimating the Effect of Highway and Traffic Engineering Measures on Road
  Safety*. Pergamon, Oxford. xv + 289 pp. ISBN 0-08-043053-8. Regression to
  the mean and the empirical Bayes method (step 2).
- AASHTO (2010). *Highway Safety Manual*, 1st edition. American Association of
  State Highway and Transportation Officials, Washington, DC. Three volumes.
  ISBN 978-1-56051-477-0. Part C gives intersection crash models as products
  of powers of the traffic on the two roads, and the empirical Bayes weighting of a model's prediction with a
  site's own count.
- Greene, W. (2008). "Functional forms for the negative binomial model for
  count data." *Economics Letters* 99(3), 585–590.
  doi:10.1016/j.econlet.2007.10.015. The variance form $\mu + \alpha\mu^{p}$
  (his equation 2-15, with $\alpha = 1/\theta$), which has the usual two
  forms as the cases $p = 1$ and $p = 2$.
- Bühlmann, H. (1967). "Experience rating and credibility." *ASTIN Bulletin*
  4(3), 199–207. doi:10.1017/S0515036100008989. The weight given to a unit's
  own record.
- Jacobsen, P. L. (2003). "Safety in numbers: more walkers and bicyclists, safer
  walking and bicycling." *Injury Prevention* 9(3), 205–209.
  doi:10.1136/ip.9.3.205. The journal's page notes a later correction.
- Elvik, R. and Bjørnskau, T. (2017). "Safety-in-numbers: a systematic review
  and meta-analysis of evidence." *Safety Science* 92, 274–282.
  doi:10.1016/j.ssci.2015.07.017. Pooled powers of about 0.5 for motor
  traffic, 0.43 for cyclists and 0.51 for pedestrians.

## Reproducing

The figures in this note come from the Los Altos study-area analysis, which
uses police crash records that are not in this repository. They also compare
against that analysis's road-and-traffic model, which is not in this
repository. The resampling ranges, the table of what each choice
contributes, the fitted values, the forecast checks, the road and traffic tests
and the dropped variants came from one-off scripts that are not included, so
they cannot be reproduced from this repository.

`make demo` runs the same hold-out check on a made-up city, and
`bike_safety_ca.checks.holdout.holdout` runs it on any table of crashes placed
at intersections.

## Data credits

Crash figures here are built from two sources:

- Transportation Injury Mapping System (TIMS), Safe Transportation Research
  and Education Center, University of California, Berkeley.
- California Crash Reporting System (CCRS), California Highway Patrol, via
  data.ca.gov.

Street data © OpenStreetMap contributors, ODbL 1.0. See "Crash
records" in `docs/guide.md` for each source's terms.
