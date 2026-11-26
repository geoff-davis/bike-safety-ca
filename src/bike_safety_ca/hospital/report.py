"""One county's report from the tables already saved.

``python -m bike_safety_ca.hospital.report --county "Santa Clara" --tables <folder>
--residents <folder> --out <folder>`` writes the report as Markdown and, with
``--pdf``, as a PDF.  It holds bicycle-injury emergency department visits per resident by
year and by age group, and the county set against the count its residents'
ages would predict at statewide rates.  The comparison of all 58 counties
(``hospital.rates.fit_prior``) needs every county's table and is not in the
sample.

Only published totals appear.  A count the source hides is shown as
"suppressed" and enters a calculation as "1 to 10"; none is worked out
from other figures.  A total stated as exact (the visits by year) cannot take
a range, so a hidden count in one stops the report.

Source of the counts: California Department of Public Health, EpiCenter –
California Injury Data Online.  Residents: U.S. Census Bureau, Population
Estimates Program.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from bike_safety_ca import links
from bike_safety_ca.hospital import epicenter, population, rates
from bike_safety_ca.hospital import tables as er

YEARS = epicenter.YEARS
STATE_YEARS = epicenter.STATEWIDE_YEARS
AGE = "Age, Summary Groups"
CAUSE = "Injury Cause Description"
ORDER = list(population.AGE_GROUPS)
TABLES = (
    "ed_total_year_under18",
    "ed_total_year_adult",
    "ed_total_age_groups",
    "hosp_total_age_groups",
    "ed_state_total_age_groups",
)


def by_year(folder: Path, residents: pd.DataFrame) -> pd.DataFrame:
    """Emergency department visits per 100,000 residents, each year."""
    # Checked for hidden cells before adding: a year with no row in one table had
    # no visits in that age range, but a blank cell is hidden, not zero.
    child = er.whole(er.table(folder, "ed_total_year_under18").set_index("Year").Count, "visits")
    adult = er.whole(er.table(folder, "ed_total_year_adult").set_index("Year").Count, "visits")
    visits = child.add(adult, fill_value=0).astype(int)
    people = residents.groupby("year").residents.sum().reindex(visits.index)
    table = pd.DataFrame({"year": visits.index, "low": visits, "high": visits})
    table["expected"] = (people / 1e5).to_numpy()  # so the "ratio" is a rate per 100,000
    found = rates.posterior(table, rates.ALONE, unit="year")
    return pd.DataFrame(
        {
            "visits": visits,
            "residents": people,
            "rate": found.raw_low,
            "rate_low": found.ratio_low,
            "rate_high": found.ratio_high,
        }
    )


def by_age(folder: Path, name: str, residents: pd.DataFrame) -> pd.DataFrame:
    """A saved table by age group as bounds on the count and on the rate per 100,000 a year."""
    saved = er.table(folder, name)
    known = rates.cells(saved, [AGE], pd.Index(saved[AGE], name=AGE))
    known["age_group"] = [population.age_group(label) for label in known.index]
    # A group with no row at all has no cases and nothing hidden.
    table = known.groupby("age_group")[["low", "high"]].sum().reindex(ORDER, fill_value=0)
    table["hidden"] = known.groupby("age_group").hidden.any().reindex(ORDER, fill_value=False)
    table["person_years"] = residents.groupby("age_group").residents.sum()
    table["rate_low"] = table.low / table.person_years * 1e5
    table["rate_high"] = table.high / table.person_years * 1e5
    return table


def state_rates(folder: Path, outcome: str, residents: pd.DataFrame) -> pd.DataFrame:
    """Lowest and highest statewide cases per resident-year by age group.

    The counts are unique visits by age group.  The table split by cause is
    not used: EpiCenter counts a visit under each cause it is coded with, so
    its rows add up to more than the visits.  A hidden cell makes its group's
    total a range.
    """
    saved = er.table(folder, f"{outcome}_state_total_age_groups")
    known = rates.cells(saved, [AGE], pd.Index(saved[AGE], name=AGE))
    groups = [population.age_group(label) for label in known.index]
    total = known.groupby(groups)[["low", "high"]].sum()
    people = residents.groupby("age_group").residents.sum()
    return total.div(people, axis=0).reindex(ORDER)


def against_state(
    folder: Path, county: str, residents: pd.DataFrame, local: pd.DataFrame
) -> dict[str, float]:
    """The county's visits against the count expected at statewide age rates."""
    first, last = STATE_YEARS
    if not set(range(first, last + 1)) <= set(local.index):
        raise ValueError(f"the county tables do not cover {first}–{last}, the statewide years")
    recent = residents[residents.year.between(first, last)]
    rate = state_rates(folder, "ed", recent)
    here = recent[recent.county.eq(county)]
    observed = int(local.visits.loc[list(range(first, last + 1))].sum())
    result: dict[str, float] = {"observed": observed}
    # The most visits expected gives the lowest ratio, and the reverse.
    for bound, column in (("high", "low"), ("low", "high")):
        expected = float(rates.expected(here, rate[column], ["county"]).sum())
        cell = pd.DataFrame({"county": [county], "low": observed, "high": observed})
        found = rates.posterior(cell.assign(expected=expected), rates.ALONE)
        result[f"expected_{column}"] = expected
        result[f"ratio_{bound}"] = float(found[f"ratio_{bound}"].iloc[0])
    return result


NOT_SHOWN = ("not shown", "not shown")
LEAST_SHOWN = rates.HIDDEN[1] + 1  # the smallest count the source publishes
SLACK = rates.HIDDEN[1] - rates.HIDDEN[0]


def withheld(table: pd.DataFrame) -> pd.Series:
    """Which groups to print nothing for, so that subtraction from a total is not handed over.

    A reader who knows the table's total could subtract every printed count
    and be left with the hidden one.  So whenever a cell is hidden, at least
    one published count is left out as well:

    - a group that joins a published cell and a hidden one prints nothing (its
      bounds would give its published part exactly);
    - the next published group after the first hidden one in the table's order
      (the one before, at the end of the table) prints nothing too, always.
      The source gives any table's total (the same query without the age
      split), so a held-back mixed group alone would be the total less every
      printed group, and its published part is in the source's table.

    ``table`` must hold every group, including any the report leaves out of
    print: a group left out is in effect held back, and its hidden cells count.

    The choice looks only at WHICH cells are hidden, published or empty, which
    the source shows anyway, and never at the size of any count.  A rule that
    tested the counts ("hold back until the margin is wide enough") would tell
    the reader the outcome of that test, and so something about the counts.
    The price is that nothing is guaranteed: if the count left out is itself
    close to 11, the remainder still narrows the hidden one.  What does hold is
    that the report prints nothing the source's own table does not.
    """
    if not table.hidden.any():
        return pd.Series(False, index=table.index)
    # All hidden: k cells hold k to 10k.  A mixed group has 11 or more published.
    pure = table.hidden & table.high.eq(rates.HIDDEN[1] * table.low)
    mixed = table.hidden & ~pure
    if (mixed & table.high.sub(table.low).ne(SLACK)).any():
        raise ValueError("a group with several hidden cells: decide by hand what to print")
    held = mixed.copy()
    published = (~table.hidden & table.low.ge(LEAST_SHOWN)).to_numpy()
    first = int(table.hidden.to_numpy().argmax())
    later = [i for i in range(first + 1, len(table)) if published[i]]
    earlier = [i for i in range(first - 1, -1, -1) if published[i]]
    if not later + earlier:
        raise ValueError("a hidden cell and nothing published to hold back beside it")
    held.iloc[(later + earlier)[0]] = True
    return held


def shown(table: pd.DataFrame, places: int = 0) -> pd.DataFrame:
    """How each group's count and rate are printed (see ``withheld``).

    A published count is printed with its rate.  A hidden one is "suppressed"
    with the rate that 1 to 10 cases would give, which says nothing new.  A
    held-back group prints "not shown" for both.
    """
    held = withheld(table)
    rows = {}
    for (group, row), hold in zip(table.iterrows(), held):
        if hold:
            rows[group] = NOT_SHOWN
        elif row.hidden:
            rows[group] = (
                "suppressed",
                f"{row.rate_low:,.{places}f} to {row.rate_high:,.{places}f}",
            )
        else:
            rows[group] = (f"{int(row.low):,}", f"{row.rate_low:,.{places}f}")
    return pd.DataFrame.from_dict(rows, orient="index", columns=["count", "rate"])


AGES_SHOWN = [age for age in ORDER if age != "0-4"]  # under-fives are mostly hidden
CREDIT = (
    "*Source: California Department of Public Health, EpiCenter – California Injury Data "
    "Online. Residents: U.S. Census Bureau, Population Estimates Program.*"
)
SHARING = (
    "Before you share this: the EpiCenter user agreement asks that CDPH be told of any "
    "publication that uses these figures (EpiCenter@cdph.ca.gov), and that CDPH/EpiCenter be "
    "credited, as every table here is."
)
HIDDEN_COUNTS = [
    "- A hidden count (one under 11) is never worked out from totals or from other cells.",
    '- It enters a calculation as "a whole number from 1 to 10", and the result is given as a '
    "range. A total stated as exact cannot take a range, so a hidden count in one stops the "
    "report instead.",
    "- No count under 11 is published, and nothing here identifies or tries to identify any "
    "person.",
]


def _ages(group: object) -> str:
    return str(group).replace("-", "–")


def _data(
    folder: Path, residents: Path, county: str, years: tuple[int, int]
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, float]]:
    """The yearly table, visits and admissions by age group, and the comparison with the state."""
    er.check_source(folder, county, years, required=TABLES)  # this county and these years
    everyone = population.residents(residents)
    if county not in set(everyone.county):
        raise ValueError(f"no California county named {county!r}")
    span = everyone[everyone.year.between(*years)]
    here = span[span.county.eq(county)]
    yearly = by_year(folder, here)
    if list(yearly.index) != list(range(years[0], years[1] + 1)):
        raise ValueError(f"the visits by year do not cover {years[0]}–{years[1]} once each")
    # Every group, under-fives too: what is held back depends on all of them.
    visits = by_age(folder, "ed_total_age_groups", here)
    admissions = by_age(folder, "hosp_total_age_groups", here)
    return yearly, visits, admissions, against_state(folder, county, everyone, yearly)


def key_points(
    county: str,
    yearly: pd.DataFrame,
    visits: pd.DataFrame,
    admissions: pd.DataFrame,
    state: dict[str, float],
) -> list[str]:
    """The three things a reader should take away, worked out from the figures."""
    if state["ratio_low"] > 1:
        standing, where = "has more visits than its ages predict", "all above 1"
    elif state["ratio_high"] < 1:
        standing, where = "has fewer visits than its ages predict", "all below 1"
    else:
        # A range that includes 1 does not show the county is like the state: it shows nothing.
        standing, where = "cannot be told apart from the state", "which includes 1"
    first, last = int(yearly.index[0]), int(yearly.index[-1])
    peak = int(str(yearly.rate.idxmax()))  # a year
    # Only groups whose count is printed: a held-back group's rate would give its count.
    seen = visits.index.isin(AGES_SHOWN) & ~visits.hidden & ~withheld(visits)
    kept = admissions.index.isin(AGES_SHOWN) & ~admissions.hidden & ~withheld(admissions)
    first_point = (
        f"- **{county} County {standing}.** In {STATE_YEARS[0]}–{STATE_YEARS[1]} its residents "
        f"made {state['observed']:,} emergency department visits for bicycle injuries, against "
        f"{_expected(state)} expected from their "
        f"ages at statewide rates: {_ratio(state)} times as many (90% range allowing for "
        f"chance: {state['ratio_low']:.2f} to {state['ratio_high']:.2f}, {where})."
    )
    # "With published counts": a held-back group may be higher, and saying so would tell.
    ages, higher = [], []
    if seen.any():
        most = str(visits[seen].rate_low.idxmax())
        ages.append(
            f"ages {_ages(most)} visit most often, at "
            f"{visits.rate_low.loc[most]:,.0f} visits per 100,000 residents a year"
        )
        higher += _higher(visits, visits.rate_low.loc[most], "visits", 0)
    if kept.any():
        stays = str(admissions[kept].rate_low.idxmax())
        ages.append(
            f"hospital admissions are most frequent at ages {_ages(stays)} "
            f"({admissions.rate_low.loc[stays]:,.1f} per 100,000 a year)"
        )
        higher += _higher(admissions, admissions.rate_low.loc[stays], "admissions", 1)
    by_age = " ".join(
        [f"Among the age groups with published counts, {', and '.join(ages)}.", *higher]
    )
    return [
        first_point,
        *([f"- **By age.** {by_age}"] if ages else []),
        f"- **Visits peaked in {peak}** at {yearly.rate.loc[peak]:.0f} per 100,000 residents and "
        f"were {yearly.rate.loc[last]:.0f} in {last}, against {yearly.rate.loc[first]:.0f} in {first}.",
    ]


def _expected(state: dict[str, float]) -> str:
    """The visits expected at statewide rates: one figure, or a range when a statewide count is hidden."""
    low, high = f"{state['expected_low']:,.0f}", f"{state['expected_high']:,.0f}"
    return low if low == high else f"{low} to {high}"


def _ratio(state: dict[str, float]) -> str:
    """The county's visits over those expected: one figure, or a range when the expected count is one.

    This is plain division.  The 90% range that allows for chance is
    ``ratio_low`` to ``ratio_high`` and is always printed under its own name.
    """
    low = f"{state['observed'] / state['expected_high']:.2f}"
    high = f"{state['observed'] / state['expected_low']:.2f}"
    return low if low == high else f"{low} to {high}"


def _higher(table: pd.DataFrame, top: float, what: str, places: int) -> list[str]:
    """A sentence for each group printed as a range wholly above ``top``, the top published rate.

    Such a group is printed as "suppressed" with the rate 1 to 10 cases would
    give, so the reader can see its range; the key point must not read as if
    the published group were higher.  A held-back group is never named.

    The figures are compared as the table prints them, to ``places`` decimal
    places: a range that starts at the printed top rate is not above it.
    """

    def printed(rate: float) -> float:
        return float(f"{rate:.{places}f}")

    ranged = table.index.isin(AGES_SHOWN) & table.hidden & ~withheld(table)
    return [
        f"The range shown for {what} at ages {_ages(age)} is higher."
        for age in table.index[ranged]
        if printed(table.rate_low[age]) > printed(top)
    ]


def plotted(table: pd.DataFrame) -> pd.DataFrame:
    """The age groups the table prints, each with how it may be drawn (see ``shown``)."""
    held = withheld(table)
    status = [
        "not shown" if hold else "suppressed" if hidden else "published"
        for hold, hidden in zip(held, table.hidden)
    ]
    rows = table[["rate_low", "rate_high"]].assign(status=status).loc[AGES_SHOWN]
    # A held-back group's rate is never handed to the chart, not even to be left undrawn.
    rows.loc[rows.status == "not shown", ["rate_low", "rate_high"]] = float("nan")
    return rows


def charts(yearly: pd.DataFrame, visits: pd.DataFrame, admissions: pd.DataFrame) -> dict[str, str]:
    from bike_safety_ca.hospital import charts as draw

    return {
        "yearly": draw.yearly(yearly, "Emergency department visits per 100,000 residents"),
        "ages": draw.by_age(
            [
                ("ED visits per 100,000 a year", plotted(visits), 0),
                ("Hospital admissions per 100,000 a year", plotted(admissions), 1),
            ]
        ),
    }


def markdown(
    folder: Path, residents: Path, county: str, years: tuple[int, int] = YEARS
) -> tuple[str, dict[str, str]]:
    """The report's Markdown and its charts (SVG), for ``pdf.write``."""
    yearly, visits, admissions, state = _data(folder, residents, county, years)
    lines = [
        f"# Bicycle injuries treated in hospital: {county} County",
        "",
        f"**{SHARING}**",
        "",
        "<!-- box -->",
        "",
        "## Key points",
        "",
        *key_points(county, yearly, visits, admissions, state),
        "",
        "<!-- /box -->",
        "",
        "**Purpose.** To help cities improve local bike safety. Cities decide where to spend "
        "limited street-safety money mostly from police crash reports, which are made mainly "
        "for collisions with motor vehicles; hospital counts also show the falls and other "
        "injuries that police reports seldom cover. A short report like this for each county "
        "would show local staff and volunteers how their county compares, which ages are hurt "
        "most, and whether things are getting better.",
        "",
        "**Source.** California Department of Public Health, EpiCenter – California Injury Data "
        f"Online: unintentional injuries to pedal cyclists, residents of {county} County, "
        f"{years[0]}–{years[1]}. Residents: U.S. Census Bureau, Population Estimates Program "
        "(1 July each year).",
        "",
        "## Emergency department visits by year",
        "",
        "### Visits per 100,000 residents",
        "",
        "<!-- chart: yearly -->",
        "",
        "*The band is the 90% range for each year's underlying rate. It is not a range for the "
        f"change between two years.* {CREDIT}",
        "",
        "| Year | Visits | Residents | Visits per 100,000 residents | 90% range |",
        "|---|---:|---:|---:|---:|",
    ]
    for year, row in yearly.iterrows():
        lines.append(
            f"| {year} | {int(row.visits):,} | {int(row.residents):,} | {row.rate:.0f} | "
            f"{row.rate_low:.0f} to {row.rate_high:.0f} |"
        )
    lines += [
        "",
        f"## By age group, {years[0]}–{years[1]} together",
        "",
        "<!-- chart: ages -->",
        "",
        f"*Rates per 100,000 residents a year; the table gives the counts.* {CREDIT}",
        "",
        "| Age | ED visits | Visits per 100,000 a year | Hospital admissions | "
        "Admissions per 100,000 a year |",
        "|---|---:|---:|---:|---:|",
    ]
    seen, kept = shown(visits), shown(admissions, 1)
    for age in AGES_SHOWN:
        lines.append(
            f"| {_ages(age)} | {seen['count'][age]} | {seen.rate[age]} | "
            f"{kept['count'][age]} | {kept.rate[age]} |"
        )
    notes = [
        "Under-fives are left out because most of their counts are hidden. Admissions are "
        "hospital stays whose record carries a bicycle-injury code (the comprehensive "
        "definition); visits that end in admission at the same hospital are counted as "
        "admissions, not as visits."
    ]
    # Only what is printed: the under-fives are in ``seen`` and ``kept`` but not in the table.
    printed = {*seen["count"][AGES_SHOWN], *kept["count"][AGES_SHOWN]}
    if "suppressed" in printed:
        notes.append(
            'A "suppressed" count is one the source hides because it is under 11. Its rate is '
            "given as the range that 1 to 10 cases would produce."
        )
    if NOT_SHOWN[0] in printed:
        notes.append(
            '"Not shown" marks a published figure left out so that a hidden count is not handed '
            "over by subtraction from a total. This is a precaution and not a guarantee."
        )
    lines += [
        "",
        f"*{' '.join(notes)}* {CREDIT}",
        "",
        f"## Against the state, {STATE_YEARS[0]}–{STATE_YEARS[1]}",
        "",
        "| | |",
        "|---|---:|",
        f"| Emergency department visits by {county} County residents | **{state['observed']:,}** |",
        f"| Visits expected if each age group had the statewide rate | **{_expected(state)}** |",
        f"| Ratio of the two (1.00 is the state average) | **{_ratio(state)}** |",
        "| 90% range for the ratio, allowing for chance | "
        f"**{state['ratio_low']:.2f} to {state['ratio_high']:.2f}** |",
        "",
        "A ratio above 1 can mean more injuries per ride or simply more riding: this is a rate "
        "per resident, not per mile cycled. The appendix explains the expected count and why "
        f"it is a range. {CREDIT}",
        "",
        "## What the full version would add",
        "",
        "With the same tables for all 58 counties, each county's ratio would be estimated "
        "together with the others, so that a small county's figure is not taken at face value, "
        'and a county would be called "higher" or "lower" than the state only when that is at '
        "least 95% sure.",
        "",
        "<!-- appendix -->",
        "",
        "## Appendix: how the figures are worked out",
        "",
        "**Counts.** Emergency department visits and hospital admissions by county residents "
        "for unintentional injuries to pedal cyclists, as published by EpiCenter. Nothing here "
        "comes from individual records.",
        "",
        "**Rates.** A count divided by the residents of the same county, age group and years, "
        "given per 100,000 residents a year. Residents are the Census Bureau's yearly county "
        "estimates, so each year's visits are set against that year's residents.",
        "",
        "**Ranges by year.** A count varies from year to year by chance even when the "
        "underlying risk is steady. The 90% range shows how far the underlying rate could "
        "plausibly be from the figure, given the size of the count.",
        "",
        "**Comparison with the state.** A county with many children will have more bicycle "
        "injuries for that reason alone, so the county is compared with what its own ages "
        "predict:",
        "",
        "> **Expected visits** = for each age group, the statewide visits per resident × the "
        "county's residents of that age, added up over the age groups",
        ">",
        "> **Ratio** = the county's visits ÷ its expected visits",
        "",
        "A ratio of 1.30 means 30% more visits than the county's ages predict. The statewide "
        "visits are counted once each, by age group; were a statewide count hidden, the "
        "expected count would be a range. The ratio is the plain division. Its 90% range "
        "allows for chance in the county's own count: it is where the underlying ratio could "
        "plausibly lie.",
        "",
        "**Small counties.** With all 58 counties, each ratio would be a blend:",
        "",
        "> **Estimated ratio** = weight × the county's own ratio + (1 − weight) × the average "
        "of all counties",
        "",
        "The weight is close to 1 for a county with many expected visits and small for a county "
        "with few, and the data from all the counties decide how fast it grows. A small "
        "county's figure is therefore pulled toward the average by as much as its small "
        "numbers warrant, and no more. The full method, with the statistical model, is in "
        f"[How counties are compared]({links.doc('county_rates_method.md')}).",
        "",
        "**Hidden counts.**",
        "",
        *HIDDEN_COUNTS,
        "",
        links.MADE_WITH,
        "",
    ]
    return "\n".join(lines), charts(yearly, visits, admissions)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="One county's hospital-treated bicycle injuries.")
    parser.add_argument("--county", required=True, help='as EpiCenter names it, e.g. "Santa Clara"')
    parser.add_argument("--tables", type=Path, required=True, help="the county's EpiCenter folder")
    parser.add_argument("--residents", type=Path, required=True, help="the Census PEP folder")
    parser.add_argument("--out", type=Path, required=True, help="folder for the report")
    parser.add_argument("--pdf", action="store_true", help="also print a PDF (needs Chrome)")
    args = parser.parse_args(argv)
    text, drawn = markdown(args.tables, args.residents, args.county)
    args.out.mkdir(parents=True, exist_ok=True)
    stem = "hospital_" + args.county.lower().replace(" ", "_")
    (args.out / f"{stem}.md").write_text(text)
    print(f"wrote {args.out / f'{stem}.md'}")
    if args.pdf:
        from bike_safety_ca.hospital import pdf

        print(f"wrote {pdf.write(stem, text, drawn, args.out)}")


if __name__ == "__main__":
    main()
