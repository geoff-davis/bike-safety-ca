"""The county rate model, on made-up counties whose true ratios are known."""

from __future__ import annotations

import re
from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from bike_safety_ca.hospital import population, rates, report


def slow(test: Callable[[], None]) -> Callable[[], None]:
    """Each of these fits several made-up states: most of a minute apiece."""
    return pytest.mark.slow(pytest.mark.timeout(600)(test))


def _counties(seed: int = 1, counties: int = 58, years: int = 9, shape: float = 6.0):
    """Made-up counties of very different sizes, each with a true ratio to the state."""
    rng = np.random.default_rng(seed)
    truth = pd.Series(
        rng.gamma(shape, 1 / shape, counties), index=[f"C{i}" for i in range(counties)]
    )
    size = np.exp(rng.normal(1.5, 1.6, counties))  # expected cases a year: under 1 to hundreds
    rows = []
    for (county, ratio), each in zip(truth.items(), size):
        for year in range(2016, 2016 + years):
            rows.append(
                {
                    "county": county,
                    "year": year,
                    "expected": each,
                    "count": rng.poisson(ratio * each),
                }
            )
    return truth, pd.DataFrame(rows)


def _published(table: pd.DataFrame) -> pd.DataFrame:
    """The table as the source would show it: counts of 1 to 10 hidden, zero rows absent."""
    shown = table[table["count"] > 0].assign(Count=lambda d: d["count"].where(d["count"] > 10))
    every = pd.MultiIndex.from_frame(table[["county", "year"]])
    known = rates.cells(shown, ["county", "year"], every)
    return known.join(table.set_index(["county", "year"]).expected).reset_index()


def test_cells_turn_published_hidden_and_absent_rows_into_bounds():
    table = pd.DataFrame({"Year": [2016, 2017], "Count": [25, None]})
    known = rates.cells(table, ["Year"], pd.Index([2016, 2017, 2018], name="Year"))
    assert known.low.to_list() == [25, 1, 0] and known.high.to_list() == [25, 10, 0]
    assert known.hidden.to_list() == [False, True, False]


def test_a_hidden_count_is_never_worked_out_from_a_total():
    # 2016 to 2018 with a published three-year total of 60: arithmetic would
    # give the hidden year as exactly 6.  Its bounds must stay 1 to 10, and
    # nothing in the module takes a total as input.
    years = pd.DataFrame({"Year": [2016, 2017, 2018], "Count": [30, 24, None]})
    known = rates.cells(years, ["Year"], pd.Index([2016, 2017, 2018], name="Year"))
    assert (known.low[2018], known.high[2018]) == (1, 10)
    assert (known.low.sum(), known.high.sum()) == (55, 64)  # not pinned to 60


def test_cells_refuse_a_small_published_count_and_a_repeated_cell():
    every = pd.Index([2016, 2017], name="Year")
    with pytest.raises(ValueError, match="published count"):
        rates.cells(pd.DataFrame({"Year": [2016], "Count": [7]}), ["Year"], every)
    with pytest.raises(ValueError, match="twice"):
        rates.cells(pd.DataFrame({"Year": [2016, 2016], "Count": [20, 30]}), ["Year"], every)
    with pytest.raises(KeyError):
        rates.cells(pd.DataFrame({"Year": [2031], "Count": [20]}), ["Year"], every)


@slow
def test_the_spread_is_recovered_with_and_without_hidden_cells():
    # With six cells in ten hidden the spread is learned less sharply, so the
    # comparison is over several made-up states, not one.
    seen, censored = [], []
    for seed in range(1, 6):
        _truth, table = _counties(seed)
        full = rates.fit_prior(table.assign(low=table["count"], high=table["count"]))
        hidden = rates.fit_prior(_published(table))
        assert full.mean == pytest.approx(1.0, abs=0.15)
        assert hidden.mean == pytest.approx(full.mean, abs=0.04)
        seen.append(full.shape)
        censored.append(hidden.shape)
    assert 4.5 < np.median(seen) < 8 and 4.5 < np.median(censored) < 8  # the truth is 6


@slow
def test_estimates_beat_the_raw_ratio_and_the_ranges_hold_the_truth():
    errors, raw_errors, inside, total = [], [], 0, 0
    for seed in range(1, 7):
        truth, table = _counties(seed)
        known = _published(table)
        found = rates.posterior(known, rates.fit_prior(known)).loc[truth.index]
        middle = (found.raw_low + found.raw_high) / 2
        errors.append(((found.ratio - truth) ** 2).mean())
        raw_errors.append(((middle - truth) ** 2).mean())
        inside += int(((found.ratio_low <= truth) & (truth <= found.ratio_high)).sum())
        total += len(truth)
    assert np.mean(errors) < 0.7 * np.mean(raw_errors)
    assert 0.84 <= inside / total <= 0.96  # a 90% range


def test_expected_counts_use_each_age_groups_statewide_rate():
    people = pd.DataFrame(
        {
            "county": ["A", "A", "B", "B"],
            "age_group": ["5-9", "10-14", "5-9", "10-14"],
            "residents": [1000, 3000, 4000, 0],
        }
    )
    rate = pd.Series({"5-9": 0.001, "10-14": 0.002})
    assert rates.expected(people, rate, ["county"]).to_dict() == {"A": 7.0, "B": 4.0}
    with pytest.raises(KeyError):
        rates.expected(people, rate.drop("5-9"), ["county"])


def test_census_file_becomes_residents_by_epicenter_age_group(monkeypatch):
    monkeypatch.setattr(population, "CODES", (1,))
    monkeypatch.setattr(population, "NAMES", ("Alder",))
    columns = {c: [10, 20] for cols in population.AGE_GROUPS.values() for c in cols}
    raw = pd.DataFrame(
        {
            "CTYNAME": "Alder County",
            "COUNTY": "001",
            "YEAR": ["1", "2"],
            "POPESTIMATE": [10 * 18, 20 * 18],
            **columns,
        }
    ).astype(str)
    tidy = population.tidy(raw, first_year=2020, first_code=2, last_year=2024)
    assert set(tidy.year) == {2020} and set(tidy.county) == {"Alder"}  # code 1 is not a July figure
    assert tidy.set_index("age_group").residents["25-44"] == 80
    with pytest.raises(ValueError, match="add up"):
        population.tidy(raw.assign(POPESTIMATE="1"), 2020, 2, 2024)
    with pytest.raises(ValueError, match="California's counties"):
        population.tidy(raw.assign(COUNTY="002"), 2020, 2, 2024)
    assert population.age_group("&lt;1") == population.age_group("1-4") == "0-4"


def _one(low, high, exposure, prior, **more):
    table = pd.DataFrame({"county": "A", "low": low, "high": high, "expected": exposure})
    return rates.posterior(table, prior, **more).loc["A"]


@pytest.mark.parametrize(
    ("counts", "exposure", "prior"),
    [
        ([30, 42], [25.0, 40.0], rates.Prior(1.1, 4.0)),
        ([0], [1.0], rates.Prior(1.0, 0.5)),  # the density is unbounded at zero
        ([0, 0], [1e-9, 2e-9], rates.Prior(1.0, 0.5)),
        ([11], [1e15], rates.Prior(1.0, 4.0)),
        ([11, 3], [1e-6, 5e-7], rates.Prior(1.2, 0.3)),
        ([20000], [18000.0], rates.Prior(0.9, 50.0)),
    ],
)
def test_the_grid_agrees_with_the_textbook_gamma(counts, exposure, prior):
    table = pd.DataFrame({"low": counts, "high": counts, "expected": exposure}, dtype=float)
    exact = stats.gamma(prior.shape + sum(counts), scale=1 / (prior.rate + sum(exposure)))
    for grid in (False, True):
        found = rates._unit(table, prior, grid=grid)
        assert found.mean == pytest.approx(exact.mean(), rel=1e-4)
        assert found.low == pytest.approx(exact.ppf(0.05), rel=1e-3)
        assert found.high == pytest.approx(exact.ppf(0.95), rel=1e-3)
        middle = exact.ppf(0.3)
        assert found.chance_above(middle) == pytest.approx(0.7, abs=1e-4)
    by_grid = rates._unit(table, prior, grid=True).log_marginal
    assert by_grid == pytest.approx(rates._unit(table, prior).log_marginal, abs=1e-4)
    assert by_grid <= 0  # the chance of a count cannot be above 1


def test_the_marginal_likelihood_matches_the_negative_binomial():
    prior = rates.Prior(mean=0.9, shape=3.0)
    table = pd.DataFrame({"county": ["A"], "low": [14], "high": [14], "expected": [12.0]})
    chance = prior.rate / (prior.rate + 12.0)
    exact = stats.nbinom.logpmf(14, prior.shape, chance)
    assert rates.log_likelihood(table, "county", prior) == pytest.approx(exact, abs=1e-8)
    # A hidden cell is the sum over the ten values it could hold.
    hidden = table.assign(low=1, high=10)
    exact = np.log(stats.nbinom.pmf(np.arange(1, 11), prior.shape, chance).sum())
    assert rates.log_likelihood(hidden, "county", prior) == pytest.approx(exact, abs=1e-6)
    # A published cell and a hidden one together: the sum over the hidden one's values.
    both = pd.DataFrame({"county": "A", "low": [14, 1], "high": [14, 10], "expected": [12.0, 5.0]})
    each = [
        rates.log_likelihood(both.assign(low=[14, n], high=[14, n]), "county", prior)
        for n in range(1, 11)
    ]
    assert rates.log_likelihood(both, "county", prior) == pytest.approx(
        np.logaddexp.reduce(each), abs=1e-6
    )


def test_the_chance_of_a_hidden_count_is_right_for_tiny_and_huge_means():
    found = rates._log_evidence(np.array([1.0]), np.array([10.0]), np.array([[1e-20, 1000.0]]))
    exact = [np.log(1e-20), -946.0168196]  # the second from summing the terms directly
    assert found[0] == pytest.approx(exact, rel=1e-6)


def test_a_hidden_cell_is_the_average_over_the_counts_it_could_hold():
    prior = rates.Prior(mean=1.0, shape=5.0)
    hidden = _one([1], [10], [6.0], prior)
    least, most = (_one([n], [n], [6.0], prior) for n in (1, 10))
    assert least.ratio < hidden.ratio < most.ratio
    assert least.ratio_low < hidden.ratio_low and hidden.ratio_high < most.ratio_high
    assert (hidden.raw_low, hidden.raw_high) == (1 / 6, 10 / 6)


def test_calls_compare_with_the_reference_not_the_fitted_mean():
    prior = rates.Prior(mean=1.3, shape=8.0)
    found = _one([1100], [1100], [1000.0], prior, reference=1.0)
    assert found.call == rates.HIGHER  # 1.1: above the state, though below the prior mean
    assert _one([900], [900], [1000.0], prior, reference=1.0).call == rates.LOWER
    assert _one([12], [12], [11.0], prior, reference=1.0).call == rates.UNCLEAR
    assert "call" not in _one([12], [12], [11.0], prior).index


@slow
def test_calls_are_rarely_wrong():
    wrong = called = 0
    for seed in range(1, 7):
        truth, table = _counties(seed)
        known = _published(table)
        found = rates.posterior(known, rates.fit_prior(known), reference=1.0).loc[truth.index]
        higher, lower = found.call.eq(rates.HIGHER), found.call.eq(rates.LOWER)
        called += int(higher.sum() + lower.sum())
        wrong += int((higher & (truth < 1)).sum() + (lower & (truth > 1)).sum())
    assert called > 60 and wrong / called < 0.05


def test_one_area_alone_is_decided_by_its_own_cells():
    found = _one([200], [200], [1000.0], rates.ALONE)
    exact = stats.gamma(200.5, scale=1 / 1000)
    assert found.ratio == pytest.approx(exact.mean()) and found.ratio_low == pytest.approx(
        exact.ppf(0.05)
    )
    hidden = _one([1], [10], [1e-7], rates.ALONE)  # tiny exposure: still the cells' answer
    assert 1e7 < hidden.ratio < 1.1e8


def test_bad_cells_and_too_few_units_are_refused():
    good = pd.DataFrame({"county": ["A"], "low": [3], "high": [3], "expected": [1.0]})
    prior = rates.Prior(1, 5)
    for change in (
        {"high": 2},
        {"high": float("nan")},
        {"expected": float("nan")},
        {"expected": 0.0},
        {"low": 2.5},
        {"high": 500},
        {"county": None},
    ):
        with pytest.raises(ValueError):
            rates.posterior(good.assign(**change), prior)
    with pytest.raises(ValueError, match="too few"):
        rates.fit_prior(good)
    with pytest.raises(ValueError):
        rates.Prior(1, 0)
    people = pd.DataFrame({"county": ["A"], "age_group": ["5-9"], "residents": [1000]})
    with pytest.raises(ValueError):
        rates.expected(people, pd.Series({"5-9": float("nan")}), ["county"])
    with pytest.raises(ValueError, match="neither"):
        rates.cells(pd.DataFrame({"Year": [2016], "Count": ["n/a"]}), ["Year"], pd.Index([2016]))


def test_counties_that_do_not_differ_fit_at_the_top_of_the_allowed_shapes():
    rng = np.random.default_rng(3)
    size = np.repeat(np.exp(rng.normal(4, 1, 30)), 4)
    count = rng.poisson(size)
    table = pd.DataFrame(
        {"county": np.repeat(np.arange(30), 4), "low": count, "high": count, "expected": size}
    )
    found = rates.fit_prior(table)
    assert found.shape > 200 and found.mean == pytest.approx(1.0, abs=0.05)


def _groups(low, high, hidden):
    table = pd.DataFrame({"low": low, "high": high, "hidden": hidden}, index=list("abcd"))
    return table.assign(rate_low=table.low / 10, rate_high=table.high / 10)


HIDDEN_FIRST = [True, False, False, False]


def test_what_is_held_back_depends_only_on_which_cells_are_hidden():
    # One wholly hidden group: the next published group goes too, whatever its size.
    for counts in ([50, 40, 70], [12, 40, 70], [900, 11, 11]):
        table = _groups([1, *counts], [10, *counts], HIDDEN_FIRST)
        assert report.withheld(table).to_list() == [False, True, False, False]
    # A group joining a published and a hidden cell is held back, and the next group too:
    # the source gives the total, so the mixed group alone is the total less the rest.
    mixed = _groups([21, 50, 60, 70], [30, 50, 60, 70], HIDDEN_FIRST)
    assert report.withheld(mixed).to_list() == [True, True, False, False]
    # A group with no cases is passed over, and at the end of the table the one before is used.
    empty = _groups([1, 0, 40, 70], [10, 0, 40, 70], HIDDEN_FIRST)
    assert report.withheld(empty).to_list() == [False, False, True, False]
    last = _groups([50, 40, 70, 1], [50, 40, 70, 10], [False, False, False, True])
    assert report.withheld(last).to_list() == [False, False, True, False]
    # Two hidden groups share the one count held back.
    two = _groups([1, 1, 40, 70], [10, 10, 40, 70], [True, True, False, False])
    assert report.withheld(two).to_list() == [False, False, True, False]


def test_printing_marks_hidden_and_held_back_figures():
    plain = _groups([40, 50, 60, 70], [40, 50, 60, 70], [False] * 4)
    assert report.shown(plain)["count"].to_list() == ["40", "50", "60", "70"]
    one = report.shown(_groups([1, 50, 40, 70], [10, 50, 40, 70], HIDDEN_FIRST))
    assert one["count"].to_list() == ["suppressed", "not shown", "40", "70"]
    assert one.rate.to_list()[:2] == ["0 to 1", "not shown"]
    with pytest.raises(ValueError, match="nothing published"):
        report.withheld(_groups([1, 0, 0, 0], [10, 0, 0, 0], HIDDEN_FIRST))
    # A group of two hidden cells and nothing published is held like one hidden cell.
    two_hidden = _groups([2, 50, 40, 70], [20, 50, 40, 70], HIDDEN_FIRST)
    assert report.withheld(two_hidden).to_list() == [False, True, False, False]
    # Several hidden cells beside published ones still need a decision by hand.
    with pytest.raises(ValueError, match="several hidden"):
        report.withheld(_groups([52, 50, 40, 70], [70, 50, 40, 70], HIDDEN_FIRST))


def test_ebike_ranges_round_outwards_and_the_comparison_names_each_case():
    from bike_safety_ca.hospital import ebike

    assert ebike._span(0.051204, 0.128811, 100, "%") == "5 to 13%"
    assert ebike._span(31.2, 38.4) == "31 to 39"
    assert ebike._span(float("nan"), float("nan"), 100, "%") == "none treated"
    rows = pd.DataFrame(
        {
            "ebike_admitted_low": [0.20, 0.01, 0.10, float("nan")],
            "ebike_admitted_high": [0.30, 0.03, 0.20, float("nan")],
            "bike_admitted_low": [0.10, 0.46, 0.15, 0.10],
            "bike_admitted_high": [0.15, 0.54, 0.25, 0.12],
        },
        index=["10-14", "15-19", "20-24", "25-44"],
    )
    text = ebike._compared(rows)
    assert "above the range for other bicycles at ages 10-14" in text
    assert "below it at ages 15-19" in text and "overlaps it at ages 20-24" in text
    assert "cannot be compared (none treated) at ages 25-44" in text
    assert "every age group" in ebike._compared(rows.iloc[:1])


def test_a_hidden_cell_with_a_shape_too_small_for_the_grid_is_refused():
    cell = pd.DataFrame({"county": ["A"], "low": [1], "high": [10], "expected": [1.0]})
    with pytest.raises(ValueError, match="prior shape"):
        rates.posterior(cell, rates.Prior(1.0, 0.0001))


def test_bad_references_rates_and_all_zero_fits_are_refused():
    good = pd.DataFrame({"county": ["A"], "low": [1], "high": [10], "expected": [1.0]})
    for reference in (float("nan"), 0.0, -1.0, float("inf")):
        with pytest.raises(ValueError, match="reference"):
            rates.posterior(good, rates.ALONE, reference=reference)
    people = pd.DataFrame({"county": "A", "age_group": ["5-9", "10-14"], "residents": [1000, 1000]})
    with pytest.raises(ValueError, match="negative"):
        rates.expected(people, pd.Series({"5-9": -0.001, "10-14": 0.002}), ["county"])
    zeros = pd.DataFrame({"county": range(12), "low": 0, "high": 0, "expected": 1.0})
    with pytest.raises(ValueError, match="no cases"):
        rates.fit_prior(zeros)


def test_a_wide_cell_with_a_very_small_shape_still_matches_the_exact_answer():
    prior = rates.Prior(1.0, 0.02)
    found = _one([0], [10], [1.0], prior)
    n = np.arange(11)
    weight = stats.nbinom.pmf(n, prior.shape, prior.rate / (prior.rate + 1))
    exact = (weight / weight.sum() * (prior.shape + n) / (prior.rate + 1)).sum()
    assert found.ratio == pytest.approx(exact, rel=1e-4)


def test_a_missing_year_of_residents_is_refused(tmp_path, monkeypatch):
    columns = {c: [5] * 4 for cols in population.AGE_GROUPS.values() for c in cols}
    raw = pd.DataFrame(
        {"CTYNAME": ["A County", "A County", "B County", "B County"], "YEAR": [2, 3] * 2}
        | {"COUNTY": [1, 1, 3, 3]}
        | {"POPESTIMATE": [90] * 4}
        | columns
    )
    raw.to_csv(tmp_path / "one.csv", index=False)
    monkeypatch.setattr(population, "COUNTIES", 2)
    monkeypatch.setattr(population, "CODES", (1, 3))
    monkeypatch.setattr(population, "NAMES", ("A", "B"))
    monkeypatch.setattr(population, "SOURCES", [("one.csv", "", 2020, 2, 2021)])
    assert len(population.residents(tmp_path)) == 2 * 2 * 9
    raw[~((raw.CTYNAME == "B County") & (raw.YEAR == 3))].to_csv(tmp_path / "one.csv", index=False)
    with pytest.raises(ValueError, match="every age group in every year"):
        population.residents(tmp_path)


def test_charts_draw_every_year_and_every_age_group():
    from bike_safety_ca.hospital import charts

    years = pd.DataFrame(
        {
            "rate": [90.0, 120.0, 100.0],
            "rate_low": [85.0, 114.0, 95.0],
            "rate_high": [95, 126, 105],
        },
        index=[2021, 2022, 2023],
    )
    drawn = charts.yearly(years, "Visits per 100,000 residents")
    assert drawn.count("<circle") == 3 and ">120<" in drawn and ">150<" in drawn
    rows = pd.DataFrame(
        {
            "ebike_admitted_low": [0.06, float("nan")],
            "ebike_admitted_high": [0.14, float("nan")],
            "bike_admitted_low": [0.02, 0.09],
            "bike_admitted_high": [0.04, 0.12],
        },
        index=["10-14", "15-19"],
    )
    drawn = charts.shares(rows)
    assert "10–14" in drawn and "15–19" in drawn and ">20%<" in drawn
    assert drawn.count('rx="4"') == 3  # no bar where nothing was treated


def test_the_page_puts_charts_where_the_text_marks_them():
    from bike_safety_ca.hospital import pdf

    text = "# Title\n\n<!-- chart: one -->\n\n*A note.*\n\n> **Ratio** = visits ÷ expected\n"
    page = pdf.page(text, {"one": "<svg></svg>"})
    assert "<figure><svg></svg><figcaption><em>A note.</em></figcaption></figure>" in page
    assert "÷" in page and "$" not in page and "\\(" not in page and pdf.CREDIT in page
    with pytest.raises(ValueError, match="no place"):
        pdf.page("# Title", {"one": "<svg></svg>"})
    with pytest.raises(ValueError, match="not supplied"):
        pdf.page(text, {})


def test_the_page_keeps_a_chart_with_its_heading_and_table():
    from bike_safety_ca.hospital import pdf

    text = "\n\n".join(
        [
            "# Title",
            "First paragraph.",
            "## Visits by year",
            "### Per 100,000",
            "<!-- chart: one -->",
            "*A note.*",
            "| Year | Visits |\n|---|---:|\n| 2016 | 40 |",
            "## By age",
            "| Age | Visits |\n|---|---:|\n| 5–9 | 40 |",
            "*A note under the table.*",
            "## Method",
            "A paragraph under a heading.",
            "A paragraph on its own.",
            "**Hidden counts.**",
            "- One point.",
        ]
    )
    page = pdf.page(text, {"one": "<svg></svg>"})
    kept = re.findall(r'<div class="keep">(.*?)</div>', page, flags=re.S)
    assert len(kept) == 4 and ".keep { break-inside: avoid; }" in pdf.STYLE
    # Heading, chart and table in one piece; the next table with its heading and note.
    assert kept[0].startswith("<h2>Visits by year</h2>") and kept[0].endswith("</table>")
    assert "<h3>" in kept[0] and "<figure>" in kept[0] and kept[0].count("<table>") == 1
    assert kept[1].startswith("<h2>By age</h2>") and kept[1].endswith("table.</em></p>")
    # No heading, and no bold lead-in to a list, is left behind at the foot of a page.
    assert kept[2] == "<h2>Method</h2>\n<p>A paragraph under a heading.</p>"
    assert kept[3].startswith("<p><strong>Hidden counts.</strong></p>") and "<ul>" in kept[3]
    assert "First paragraph." not in "".join(kept) and "on its own" not in "".join(kept)


def test_key_points_follow_the_figures():
    yearly = pd.DataFrame({"rate": [80.0, 110.0, 90.0]}, index=[2016, 2020, 2024])
    ages = pd.DataFrame(
        {"hidden": [False, False], "rate_low": [300.0, 100.0]}, index=["10-14", "25-44"]
    )
    state = {"observed": 500, "expected_low": 300.0, "expected_high": 320.0}
    above = report.key_points(
        "Alder", yearly, ages, ages, state | {"ratio_low": 1.4, "ratio_high": 1.8}
    )
    assert above[0].startswith("- **Alder County has more")
    assert "has more visits than its ages predict" in above[0]
    assert "cannot be told apart" not in above[0]
    # 500 visits against 300 to 320 expected is plain division; the 90% range is named as one.
    assert above[0].endswith(
        "at statewide rates: 1.56 to 1.67 times as many (90% range allowing for chance: 1.40 to "
        "1.80, all above 1)."
    )
    assert (
        "Among the age groups with published counts, ages 10–14 visit most often" in above[1]
        and "peaked in 2020" in above[2]
    )
    # Visits and admissions in one sentence, with the scope said once.
    assert above[1].count("Among the age groups") == 1 and "a year. " not in above[1]
    assert ", and hospital admissions are most frequent at ages 10–14 (300.0 per" in above[1]
    below = report.key_points(
        "Alder", yearly, ages, ages, state | {"ratio_low": 0.5, "ratio_high": 0.99}
    )
    assert below[0].startswith("- **Alder County has fewer visits than its ages predict.**")
    assert below[0].endswith("(90% range allowing for chance: 0.50 to 0.99, all below 1).")


def test_a_range_that_includes_1_is_not_called_in_line_with_the_state():
    yearly = pd.DataFrame({"rate": [80.0, 110.0, 90.0]}, index=[2016, 2020, 2024])
    ages = pd.DataFrame(
        {"hidden": [False, False], "rate_low": [300.0, 100.0]}, index=["10-14", "25-44"]
    )
    state = {"observed": 26, "expected_low": 20.0, "expected_high": 20.0}
    # 26 visits against 20 expected: a ratio of 1.3 that could be anything from 0.92 to 1.77.
    for low, high in ((0.92, 1.77), (1.0, 1.4), (0.6, 1.0)):
        first = report.key_points(
            "Alder", yearly, ages, ages, state | {"ratio_low": low, "ratio_high": high}
        )[0]
        assert first.startswith("- **Alder County cannot be told apart from the state.**")
        assert "in line with" not in first and " more " not in first and "fewer" not in first
        # 26 / 20 is exactly 1.30; only the range that allows for chance reaches 1.
        assert first.endswith(
            "against 20 to 20 expected from their ages at statewide rates: 1.30 times as many "
            f"(90% range allowing for chance: {low:.2f} to {high:.2f}, which includes 1)."
        )
        assert "could be anywhere" not in first


def test_key_points_never_name_a_group_held_back_or_left_out():
    yearly = pd.DataFrame({"rate": [80.0, 110.0, 90.0]}, index=[2016, 2020, 2024])
    state = {"observed": 500, "expected_low": 300.0, "expected_high": 320.0}
    state |= {"ratio_low": 0.9, "ratio_high": 1.1}

    def ages(rates, hidden, low, high):
        index = ["0-4", "5-9", "10-14", "15-19"]
        frame = {"low": low, "high": high, "hidden": hidden, "rate_low": rates}
        return pd.DataFrame(frame, index=index)

    # 0-4 mixed (13 to 22) holds back 5-9, which has the highest rate.
    held = ages([50.0, 400.0, 100.0, 90.0], HIDDEN_FIRST, [13, 40, 30, 20], [22, 40, 30, 20])
    # 0-4 is not printed at all, though its rate is highest.
    left = ages([900.0, 80.0, 100.0, 90.0], [False] * 4, [60, 40, 30, 20], [60, 40, 30, 20])
    # 10-14 is hidden, though its rate is highest; 15-19 is held back beside it.
    hidden = ages(
        [50.0, 80.0, 400.0, 90.0], [False, False, True, False], [60, 40, 1, 20], [60, 40, 10, 20]
    )
    for table, named in ((held, "10–14"), (left, "10–14"), (hidden, "5–9")):
        line = next(
            p for p in report.key_points("Alder", yearly, table, table, state) if "By age" in p
        )
        assert f"ages {named} visit most often" in line
        assert f"admissions are most frequent at ages {named}" in line
        assert line.startswith("- **By age.** Among the age groups with published counts, ")
    # Each outcome uses its own table's mask: 5-9 is printed for visits, held back for admissions.
    line = next(p for p in report.key_points("Alder", yearly, left, held, state) if "By age" in p)
    assert "admissions are most frequent at ages 10–14" in line


def test_the_age_key_point_does_not_contradict_a_group_shown_as_a_range():
    yearly = pd.DataFrame({"rate": [80.0, 110.0, 90.0]}, index=[2016, 2020, 2024])
    state = {"observed": 500, "expected_low": 300.0, "expected_high": 320.0}
    state |= {"ratio_low": 0.9, "ratio_high": 1.1}

    def ages(rate_of_hidden, top=30.0):
        # 85+ is one hidden cell, printed as "suppressed" with its range; 65-84 is held back.
        frame = {
            "low": [60, 30, 40, 1],
            "high": [60, 30, 40, 10],
            "hidden": [False, False, False, True],
            "rate_low": [50.0, top, 20.0, rate_of_hidden],
            "rate_high": [50.0, top, 20.0, 10 * rate_of_hidden],
        }
        return pd.DataFrame(frame, index=["0-4", "10-14", "65-84", "85+"])

    above, under = ages(100.0), ages(5.0)
    assert report.shown(above)["count"].to_list() == ["60", "30", "not shown", "suppressed"]
    line = report.key_points("Alder", yearly, above, under, state)[1]
    assert "ages 10–14 visit most often, at 30 visits" in line
    # Its whole range (100 and up) is above 30, and the table shows that.
    assert line.endswith(" The range shown for visits at ages 85+ is higher.")
    assert "for admissions" not in line and "65–84" not in line
    line = report.key_points("Alder", yearly, under, above, state)[1]
    assert line.endswith(" The range shown for admissions at ages 85+ is higher.")
    assert "for visits" not in line

    # A near-tie: 30.30 prints as 30 and the hidden group as "30 to 304", which is not higher.
    tie = ages(30.40, top=30.30)
    assert report.shown(tie).loc[["10-14", "85+"]].to_numpy().tolist() == [
        ["30", "30"],
        ["suppressed", "30 to 304"],
    ]
    line = report.key_points("Alder", yearly, tie, under, state)[1]
    assert "is higher" not in line
    # Admissions print to one place, where 30.4 is above 30.3.
    assert report.shown(tie, 1).rate["85+"] == "30.4 to 304.0"
    line = report.key_points("Alder", yearly, under, tie, state)[1]
    assert line.endswith(" The range shown for admissions at ages 85+ is higher.")
    # To one place 30.44 against 30.36 is 30.4 against 30.4: not higher.
    line = report.key_points("Alder", yearly, under, ages(30.44, top=30.36), state)[1]
    assert "is higher" not in line
