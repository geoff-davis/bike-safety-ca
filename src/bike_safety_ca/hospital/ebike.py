"""A statewide report on electric bicycles from the one statewide table already saved.

``python -m bike_safety_ca.hospital.ebike --tables <folder> --residents <folder>
--out <folder>`` writes it as Markdown and, with ``--pdf``, as a PDF.  The table
is the statewide one saved (cause by age group, 2023–2024, the first full years in which hospital
records could name an electric bicycle).

Most e-bike cells are hidden (a count from 1 to 10), so every figure is a
range: the least and the most the published and hidden cells can add up to.
The ranges make no allowance for chance, and the report says so wherever it
prints one.  No hidden count is worked out from other figures.

Source of the counts: California Department of Public Health, EpiCenter –
California Injury Data Online.  Residents: U.S. Census Bureau, Population
Estimates Program.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd

from bike_safety_ca import links
from bike_safety_ca.hospital import population, rates
from bike_safety_ca.hospital import tables as er
from bike_safety_ca.hospital.report import (
    AGE,
    CAUSE,
    CREDIT,
    HIDDEN_COUNTS,
    SHARING,
    STATE_YEARS,
    _ages,
)

EBIKE = "electric (assisted) bicycle"
# Younger and older groups are almost wholly hidden.
GROUPS = ["10-14", "15-19", "20-24", "25-44", "45-64", "65-84"]
HIDDEN_MAX = rates.HIDDEN[1]
STATE_TABLES = (
    "ed_state_bike_cause_age_groups",
    "hosp_state_bike_cause_age_groups",
    "ed_state_total_age_groups",
    "hosp_state_total_age_groups",
)
# Printed wherever a range is: a reader takes a narrow range for a sure finding.
NOT_CHANCE = (
    "The ranges cover hidden counts only, not chance: a narrow range is not a precise finding, "
    "and small groups can differ by chance alone."
)


def counts(folder: Path, outcome: str) -> pd.DataFrame:
    """Lowest and highest count by age group, for e-bikes and for other bicycles."""
    saved = er.table(folder, f"{outcome}_state_bike_cause_age_groups")
    known = rates.cells(saved, [CAUSE, AGE], pd.MultiIndex.from_frame(saved[[CAUSE, AGE]]))
    cause = known.index.get_level_values(CAUSE)
    kind = pd.Series(cause.str.contains(EBIKE, case=False, regex=False), index=known.index)
    kind = kind.map({True: "ebike", False: "bike"})
    age = known.index.get_level_values(AGE)
    # Every kind and age group, with zero where the table has no row at all.
    every = pd.MultiIndex.from_product([["ebike", "bike"], GROUPS])
    by = [kind.to_numpy(), age]
    total = known.groupby(by)[["low", "high"]].sum().reindex(every, fill_value=0)
    # A range from a single hidden cell would give away the published cells beside it.
    if known.hidden.groupby(by).sum().reindex(every, fill_value=0).eq(1).any():
        raise ValueError("an age group with exactly one hidden cell: do not print its range")
    return pd.DataFrame(total.unstack(0)).reindex(GROUPS)


def table(folder: Path, residents: Path) -> pd.DataFrame:
    """One row per age group: counts, shares admitted and visits per resident, as ranges."""
    visits, stays = counts(folder, "ed"), counts(folder, "hosp")
    everyone = population.residents(residents)
    people = everyone[everyone.year.between(*STATE_YEARS)].groupby("age_group").residents.sum()
    rows = pd.DataFrame(index=GROUPS)
    for kind in ("ebike", "bike"):
        for bound, other in (("low", "high"), ("high", "low")):
            rows[f"{kind}_visits_{bound}"] = visits[bound, kind]
            rows[f"{kind}_stays_{bound}"] = stays[bound, kind]
            # The lowest share pairs the fewest admissions with the most visits.
            treated = stays[bound, kind] + visits[other, kind]
            rows[f"{kind}_admitted_{bound}"] = stays[bound, kind] / treated.where(treated > 0)
    for bound in ("low", "high"):
        treated = rows[f"ebike_visits_{bound}"] + rows[f"ebike_stays_{bound}"]
        # ``people`` is residents summed over the years, so this is a rate per year.
        rows[f"ebike_rate_{bound}"] = treated / people.reindex(GROUPS) * 1e5
    return rows


def _span(low: float, high: float, scale: float = 1, unit: str = "") -> str:
    """A range in whole numbers, rounded outwards so the print never claims more than is known."""
    if math.isnan(low) or math.isnan(high):
        return "none treated"
    one, two = f"{math.floor(low * scale):,}", f"{math.ceil(high * scale):,}"
    return f"{one}{unit}" if one == two else f"{one} to {two}{unit}"


def _compared(rows: pd.DataFrame) -> str:
    """What the unrounded ranges say about e-bikes against other bicycles, group by group."""
    above = rows.ebike_admitted_low > rows.bike_admitted_high
    below = rows.ebike_admitted_high < rows.bike_admitted_low
    unknown = rows[["ebike_admitted_low", "bike_admitted_low"]].isna().any(axis=1)
    overlap = ~(above | below | unknown)
    if above.all():
        return "In every age group the whole range for e-bikes lies above the range for other bicycles."
    parts = [
        f"{text} at ages {', '.join(which.index[which])}"
        for which, text in (
            (above, "lies wholly above the range for other bicycles"),
            (below, "lies wholly below it"),
            (overlap, "overlaps it"),
            (unknown, "cannot be compared (none treated)"),
        )
        if which.any()
    ]
    return f"The range for e-bikes {'; '.join(parts)}."


def admission_ratio(folder: Path) -> tuple[float, float]:
    """Lowest and highest ratio of e-bike admissions to those expected at ordinary-bike shares.

    Expected admissions: in each age group, the e-bike injuries treated times
    the share of other cyclists of that age who were admitted.  Each hidden
    cell holds 1 to 10.  The low ratio pairs the fewest e-bike admissions with
    the most e-bike visits and the highest ordinary-bike share, the high ratio
    the reverse; both are rounded outwards to two places.
    """
    state = {}
    for outcome in ("ed", "hosp"):
        d = er.table(folder, f"{outcome}_state_bike_cause_age_groups")
        d = d[d[AGE].isin(GROUPS)]
        kind = d[CAUSE].str.contains(EBIKE, case=False, regex=False)
        for name, part in (("ebike", d[kind]), ("bike", d[~kind])):
            cells = part.groupby(AGE).Count
            hidden = cells.apply(lambda c: c.isna().sum())
            for level, each in (("low", 1), ("high", HIDDEN_MAX)):
                state[outcome, name, level] = (cells.sum() + each * hidden).reindex(
                    GROUPS,
                    fill_value=0,  # no row at all: none treated
                )

    def share(name: str, admitted: str, visits: str) -> pd.Series:
        h, e = state["hosp", name, admitted], state["ed", name, visits]
        return h / (h + e)

    found = {}
    for level, (h, e, ordinary) in {
        "low": ("low", "high", ("high", "low")),
        "high": ("high", "low", ("low", "high")),
    }.items():
        treated = state["hosp", "ebike", h] + state["ed", "ebike", e]
        compare = share("bike", *ordinary)
        if compare[treated > 0].isna().any():
            raise ValueError("an age group with e-bike injuries and no other bicycles to compare")
        ratio = float(state["hosp", "ebike", h].sum() / (treated * compare).sum())
        # More e-bike admissions raise both the count and the expected count.  The
        # pairing gives true bounds only while the first effect wins, which is
        # while each ordinary-bike share times the ratio is under 1.
        if (share("bike", *ordinary) * ratio).max() >= 1:
            raise ValueError("the e-bike admission ratio's range is not a bound here")
        found[level] = ratio
    return math.floor(found["low"] * 100) / 100, math.ceil(found["high"] * 100) / 100


def overlap(folder: Path) -> dict[str, tuple[int, int, int, int]]:
    """For ED visits and admissions, all ages: the cause rows' least and most sum, then the
    least and most count of unique visits.

    EpiCenter counts a visit under each cause it is coded with, so the cause
    rows can add up to more than the visits; the two side by side show how
    much.  Hidden cells hold 1 to 10, as everywhere.
    """
    found = {}
    for outcome in ("ed", "hosp"):
        by_cause = er.table(folder, f"{outcome}_state_bike_cause_age_groups")
        rows = rates.cells(by_cause, [CAUSE, AGE], pd.MultiIndex.from_frame(by_cause[[CAUSE, AGE]]))
        unique = er.table(folder, f"{outcome}_state_total_age_groups")
        visits = rates.cells(unique, [AGE], pd.Index(unique[AGE], name=AGE))
        found[outcome] = (
            int(rows.low.sum()),
            int(rows.high.sum()),
            int(visits.low.sum()),
            int(visits.high.sum()),
        )
    return found


def _overlap(folder: Path) -> str:
    """The sentence comparing the cause rows with the unique visits."""
    parts = []
    for outcome, what in (("ed", "emergency department visits"), ("hosp", "admissions")):
        rows_low, rows_high, low, high = overlap(folder)[outcome]
        parts.append(
            f"{_span(rows_low, rows_high)} {what} in the cause rows against "
            f"{_span(low, high)} counted once each"
        )
    return f"Over all ages, {parts[0]}, and {parts[1]}."


def _data(folder: Path, residents: Path) -> tuple[pd.DataFrame, float, float]:
    """The table by age group and the lowest and highest ratio of actual to expected admissions."""
    er.check_source(folder, None, STATE_YEARS, STATE_YEARS, required=STATE_TABLES)
    low, high = admission_ratio(folder)
    return table(folder, residents), low, high


def key_points(rows: pd.DataFrame, low: float, high: float) -> list[str]:
    """The three things a reader should take away, worked out from the figures."""
    top = str(rows.ebike_rate_low.idxmax())
    clear = (rows.ebike_rate_high.drop(top) < rows.ebike_rate_low.loc[top]).all()
    rate = _span(rows.ebike_rate_low.loc[top], rows.ebike_rate_high.loc[top])
    verdict = "more" if low > 1 else "fewer" if high < 1 else "possibly more or fewer"
    first, last = _ages(rows.index[0]).split("–")[0], _ages(rows.index[-1]).split("–")[-1]
    return [
        # Scoped to the groups in the table: the ages left out are hidden, not lower.
        f"- **Among the age groups shown (ages {first} to {last}), ages {_ages(top)} have "
        f"{'the highest' if clear else 'one of the highest'} e-bike injury rates:** {rate} "
        "treated in hospital per 100,000 residents a year.",
        f"- **Share admitted.** {_compared(rows)}",
        f"- **Allowing for age, e-bike riders had {verdict} admissions than other cyclists "
        f"would have had:** {low:.2f} to {high:.2f} times as many, before any allowance for "
        "chance.",
        "",
        f"*{NOT_CHANCE}*",
    ]


def charts(rows: pd.DataFrame) -> dict[str, str]:
    from bike_safety_ca.hospital import charts as draw

    return {"shares": draw.shares(rows)}


def markdown(folder: Path, residents: Path) -> tuple[str, dict[str, str]]:
    """The report's Markdown and its charts (SVG), for ``pdf.write``."""
    rows, low, high = _data(folder, residents)
    first, last = STATE_YEARS
    lines = [
        f"# Electric bicycle injuries treated in hospital: California, {first}–{last}",
        "",
        f"**{SHARING}**",
        "",
        "<!-- box -->",
        "",
        "## Key points",
        "",
        *key_points(rows, low, high),
        "",
        "<!-- /box -->",
        "",
        "**Purpose.** To help cities improve local bike safety. Cities are being asked to make "
        "rules about electric bicycles, above all for teenagers, with little evidence to hand. "
        "Hospital records have been able to name an electric bicycle since October 2022, so "
        "they can now say who is hurt and how badly.",
        "",
        "**Source.** California Department of Public Health, EpiCenter – California Injury Data "
        f"Online: unintentional injuries to pedal cyclists, all California residents, {first}–"
        f"{last}, by cause and age group. Residents: U.S. Census Bureau, Population Estimates "
        "Program.",
        "",
        "## Are e-bike injuries more serious?",
        "",
        "### Share of hospital-treated injuries that were admissions, by age group",
        "",
        "<!-- chart: shares -->",
        "",
        "*Each bar runs from the lowest to the highest share the published counts allow. It "
        f"covers hidden counts only, not chance.* {CREDIT}",
        "",
        f"{_compared(rows)} The share admitted differs with age, so the fair comparison is "
        "within age groups. Putting the groups together, and setting e-bike admissions against "
        "the number there would have been had e-bike riders been admitted as often as other "
        f"cyclists of the same age, the ratio of actual to expected is **{low:.2f} to "
        f"{high:.2f}**. {NOT_CHANCE}",
        "",
        "## By age group",
        "",
        "| Age | E-bike injuries treated per 100,000 residents a year | "
        "Share admitted, e-bikes | Share admitted, other bicycles |",
        "|---|---:|---:|---:|",
    ]
    for age, row in rows.iterrows():
        lines.append(
            f"| {_ages(age)} | {_span(row.ebike_rate_low, row.ebike_rate_high)} | "
            f"{_span(row.ebike_admitted_low, row.ebike_admitted_high, 100, '%')} | "
            f"{_span(row.bike_admitted_low, row.bike_admitted_high, 100, '%')} |"
        )
    lines += [
        "",
        "*Every figure is a range because most e-bike counts are hidden (under 11). "
        f"{NOT_CHANCE} Ranges are rounded outwards, so two that are apart can look as if they "
        "meet. Ages under 10 and over 84 are left out because almost all their counts are "
        f"hidden.* {CREDIT}",
        "",
        "## Limits",
        "",
        "- **Ranges are not margins of error.** Each range is the least and the most the hidden "
        "counts allow. None allows for chance, which matters most where the counts are small.",
        "- **Coding is new.** A record names an e-bike only if the clinician and coder noted "
        "it, so cases may be missing, and a change in how fully e-bikes are recorded would "
        "look like a change in injuries.",
        "- **Per resident, not per rider.** There is no count of e-bike riders or miles, so "
        "these are not risks of riding.",
        "- **Visits, not people.** One person can have several.",
        "- **Causes can overlap.** A visit coded under two causes is counted under each, so "
        "the counts by cause can run a little above the visits (see the appendix).",
        "- **A more serious mix, not proof of cause.** Riders who are admitted may be more "
        "likely to have the bicycle type recorded, which would raise the e-bike share admitted.",
        "",
        "<!-- appendix -->",
        "",
        "## Appendix: how the figures are worked out",
        "",
        "**Counts.** The source table gives emergency department visits and hospital admissions "
        "by cause and age group. It is split into some sixty causes, and most of the e-bike "
        "cells are hidden, so each total below is a range: the least and the most the published "
        "and hidden cells can add up to. EpiCenter counts a visit under each cause it is coded "
        f"with, so these totals can run a little above the visits. {_overlap(folder)}",
        "",
        "| Age | E-bike ED visits | E-bike admissions |",
        "|---|---:|---:|",
    ]
    for age, row in rows.iterrows():
        lines.append(
            f"| {_ages(age)} | {_span(row.ebike_visits_low, row.ebike_visits_high)} | "
            f"{_span(row.ebike_stays_low, row.ebike_stays_high)} |"
        )
    lines += [
        "",
        CREDIT,
        "",
        "**Treated.** Emergency department visits plus admissions. A visit that ends in "
        "admission at the same hospital is counted once, as an admission. Admissions use the "
        "comprehensive definition (a bicycle-injury code anywhere on the record).",
        "",
        "**Share admitted.**",
        "",
        "> **Share admitted** = admissions ÷ (admissions + emergency department visits)",
        "",
        "The lowest share pairs the fewest admissions with the most visits, and the highest "
        "the reverse.",
        "",
        "**Allowing for age.**",
        "",
        "> **Expected admissions** = for each age group, the e-bike injuries treated × the "
        "share admitted among other cyclists of that age, added up over the age groups",
        ">",
        "> **Ratio** = actual e-bike admissions ÷ expected admissions",
        "",
        "**Hidden counts.**",
        "",
        *HIDDEN_COUNTS,
        "",
        links.MADE_WITH,
        "",
    ]
    return "\n".join(lines), charts(rows)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Electric bicycle injuries, all of California.")
    parser.add_argument("--tables", type=Path, required=True, help="an EpiCenter folder")
    parser.add_argument("--residents", type=Path, required=True, help="the Census PEP folder")
    parser.add_argument("--out", type=Path, required=True, help="folder for the report")
    parser.add_argument("--pdf", action="store_true", help="also print a PDF (needs Chrome)")
    args = parser.parse_args(argv)
    text, drawn = markdown(args.tables, args.residents)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "hospital_ebike_california.md").write_text(text)
    print(f"wrote {args.out / 'hospital_ebike_california.md'}")
    if args.pdf:
        from bike_safety_ca.hospital import pdf

        print(f"wrote {pdf.write('hospital_ebike_california', text, drawn, args.out)}")


if __name__ == "__main__":
    main()
