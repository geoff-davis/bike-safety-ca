from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bike_safety_ca import ADULT, CAR, CHILD, CYCLISTS, config
from bike_safety_ca.checks.holdout import holdout, notes, report
from bike_safety_ca.model.crash_history import (
    fit_street_model,
    rank_intersections,
    rank_score,
    top_share,
)
from bike_safety_ca.synthetic import City, make_city

ROOT = Path(__file__).resolve().parents[1]


def test_city_is_repeatable_and_complete() -> None:
    a, b = make_city(seed=3, size=12), make_city(seed=3, size=12)
    pd.testing.assert_frame_equal(a.crashes, b.crashes)
    assert len(a.sites) == 144 and set(a.streets) == set(a.sites.index)
    assert all(len(names) == 2 for names in a.streets.values())
    assert set(a.crashes.group) == {CHILD, ADULT, CAR}
    assert a.crashes.site.isin(a.sites.index).all()


def test_model_ranks_the_true_rates_better_than_the_raw_record() -> None:
    city = make_city()
    crashes = city.crashes
    index = city.sites.index
    bike = crashes[crashes.group.isin([CHILD, ADULT])].groupby("site").size()
    car = crashes[crashes.group == CAR].groupby("site").size()
    bike, car = bike.reindex(index, fill_value=0), car.reindex(index, fill_value=0)
    model = fit_street_model(bike, car, city.streets)["sites"].eb
    truth = city.sites.bike_rate
    assert model.corr(truth, method="spearman") > bike.corr(truth, method="spearman") + 0.05


def test_holdout_runs_end_to_end_and_the_model_beats_past_crashes() -> None:
    city = make_city()
    area = city.sites.index[city.sites.in_city]
    table = holdout(city.crashes, city.sites.index, city.streets, areas={"City": area})
    assert set(table.area) == {"All intersections", "City"}
    # Three windows and two areas; five rankings for all cyclists, six for children.
    assert len(table) == 3 * 2 * (5 + 6)
    everywhere = table[(table.area == "All intersections") & (table.outcome == "All cyclists")]
    mean = everywhere.groupby("ranking")["rank score"].mean()
    assert mean["Street-length model"] > mean["Past bike crashes"] + 0.03
    assert mean["Street-length model"] > 0.6


def test_too_few_later_crashes_are_counted_but_not_scored() -> None:
    city = make_city()
    area = city.sites.index[city.sites.in_city]
    table = holdout(city.crashes, city.sites.index, city.streets, areas={"City": area})
    figures = ["rank score", "found in top 25", "found in top 50", "found in top 100"]
    few = table["later crashes"] < 30
    # Only children inside the city in the two-year window: 26 later crashes.
    assert table[few].drop_duplicates(["tested on", "outcome", "area"])[
        ["tested on", "outcome", "area", "later crashes"]
    ].to_numpy().tolist() == [["2021–2022", "Cyclists 18 or under", "City", 26]]
    assert table.loc[few, figures].isna().all().all()
    assert table.loc[~few, figures].notna().all().all()

    # The floor can be moved: with none every row is scored, with a high one none is.
    every = holdout(city.crashes, city.sites.index, city.streets, areas={"City": area}, min_later=0)
    assert every[figures].notna().all().all()
    assert every.loc[~few.to_numpy(), figures].equals(table.loc[~few, figures])
    none = holdout(city.crashes, city.sites.index, city.streets, min_later=10**6)
    assert none[figures].isna().all().all() and (none["later crashes"] > 0).all()


def test_children_are_also_scored_on_the_all_cyclist_ranking() -> None:
    city = make_city()
    table = holdout(city.crashes, city.sites.index, city.streets, min_later=0)
    keys = ["trained through", "area"]
    figures = ["later crashes", "rank score", "found in top 25", "found in top 50"]
    model = table[table.ranking.eq("Street-length model")]
    borrowed = table[table.ranking.eq("All-cyclist ranking")]
    assert set(borrowed.outcome) == {"Cyclists 18 or under"} and len(borrowed) == 3
    children = model[model.outcome.eq("Cyclists 18 or under")].set_index(keys)
    borrowed = borrowed.set_index(keys)
    # The same later crashes, found by a different ranking: the one fitted to every cyclist.
    assert borrowed["later crashes"].equals(children["later crashes"])
    assert not borrowed["rank score"].equals(children["rank score"])
    assert (borrowed["training crashes"] == children["training crashes"]).all()
    for through in (2018, 2020, 2022):
        row = borrowed.xs(through, level="trained through").iloc[0].to_dict()
        early = city.crashes[city.crashes.year.le(through)]
        late = city.crashes[city.crashes.year.gt(through) & city.crashes.group.eq(CHILD)]

        def at(rows: pd.DataFrame) -> pd.Series:
            return rows.groupby("site").size().reindex(city.sites.index, fill_value=0)

        if through < 2022:  # the first two windows are tested on years up to 2022 only
            late = late[late.year.le(2022)]
        ranked = rank_intersections(
            at(early[early.group.isin(CYCLISTS)]), at(early[early.group.eq(CAR)]), city.streets
        )
        assert row["rank score"] == round(rank_score(ranked["score"], at(late)), 3)
        # The counts at the top are the all-cyclist ranking's own, not the child model's.
        for k in (25, 50, 100):
            assert row[f"found in top {k}"] == round(top_share(ranked["score"], at(late), k), 1)
        own = children.xs(through, level="trained through").iloc[0]
        # A different ranking from the child model's.  (One count can agree by chance: at
        # spread power 1 both find 15 in the top 100 in one window.)
        assert any(row[name] != own[name] for name in figures[1:] + ["found in top 100"])
        assert row["training crashes"] == int(early.group.eq(CHILD).sum())

    # Where every cyclist is a child the two rankings are one and the same.
    only = city.crashes[city.crashes.group.isin([CHILD, CAR])]
    same = holdout(only, city.sites.index, city.streets, min_later=0)
    child = same[same.outcome.eq("Cyclists 18 or under")]
    assert (
        child[child.ranking.eq("All-cyclist ranking")][figures].to_numpy().tolist()
        == child[child.ranking.eq("Street-length model")][figures].to_numpy().tolist()
    )


@pytest.mark.filterwarnings(  # the earlier fitted formula struggles on the thinned crashes
    "ignore::RuntimeWarning",
    "ignore::statsmodels.tools.sm_exceptions.ConvergenceWarning",
    "ignore::statsmodels.tools.sm_exceptions.HessianInversionWarning",
)
def test_the_note_points_children_to_the_all_cyclist_ranking_when_they_are_too_few() -> None:
    city = make_city()
    crashes = city.crashes
    children = crashes[crashes.group.eq(CHILD)]
    thinned = pd.concat([crashes[crashes.group.ne(CHILD)], children.iloc[::8]])
    table = holdout(thinned, city.sites.index, city.streets)
    lines = notes(table)
    # Each window has fewer than 100 child crashes to fit and enough of all cyclists.
    assert len(lines) == 3 and all("Cyclists 18 or under" in line for line in lines)
    assert all(
        line.endswith("rank this group by the all-cyclist ranking instead") for line in lines
    )
    assert "trained through 2018 (" in lines[0] and " crashes)" in lines[0]
    assert notes(holdout(crashes, city.sites.index, city.streets)) == []

    # A fit that failed on enough crashes is not a shortage: no advice to switch rankings.
    failed = table.assign(**{"training crashes": 150})
    assert all("could not be fitted" in line and "instead" not in line for line in notes(failed))

    # Too few of every cyclist: there is no other ranking to point to.
    few = holdout(crashes.iloc[::40], city.sites.index, city.streets)
    everyone = [line for line in notes(few) if "All cyclists" in line]
    assert everyone and not any("instead" in line for line in everyone)


def test_the_report_shows_the_count_where_there_is_no_score_and_averages_the_rest() -> None:
    row = {"area": "City", "outcome": "All cyclists", "ranking": "Past bike crashes"}
    table = pd.DataFrame(
        [
            {**row, "tested on": "2019–2022", "later crashes": 40, "rank score": 0.7},
            {**row, "tested on": "2021–2022", "later crashes": 12, "rank score": float("nan")},
            {**row, "tested on": "2023–latest", "later crashes": 35, "rank score": 0.8},
            {**row, "outcome": "Children", "tested on": "2019–2022", "later crashes": 3},
            {**row, "outcome": "Children", "tested on": "2021–2022", "later crashes": 0},
            {**row, "outcome": "Children", "tested on": "2023–latest", "later crashes": 5},
        ]
    )
    cyclists, children = report(table).splitlines()[2:]
    assert all(cell in cyclists for cell in ("0.700", "too few (12)", "0.800"))
    assert cyclists.split()[-1] == "0.750"  # the mean of the two scored periods
    assert all(cell in children for cell in ("too few (3)", "too few (0)", "too few (5)"))
    assert children.endswith("none scored")  # no period scored, so no mean


@pytest.mark.filterwarnings(  # two intersections: nothing to fit
    "ignore::RuntimeWarning",
    "ignore::statsmodels.tools.sm_exceptions.PerfectSeparationWarning",
)
def test_the_report_tells_a_missing_score_on_enough_crashes_from_too_few() -> None:
    # Two intersections, both with later crashes: enough crashes, nothing to compare.
    table = holdout(
        pd.DataFrame(
            {"site": [0] * 20 + [1] * 20, "year": [2017] * 10 + [2023] * 30, "group": ADULT}
        ),
        pd.Index([0, 1]),
        {0: frozenset({"A"}), 1: frozenset({"B"})},
        windows=[(2018, 2019, None)],
    )
    everyone = table[table.outcome.eq("All cyclists") & table.ranking.eq("Past bike crashes")]
    assert everyone["later crashes"].tolist() == [30] and everyone["rank score"].isna().all()
    printed = report(table)
    assert "no score" in printed and "too few (30)" not in printed
    assert "too few (0)" in printed  # no child crashes at all


def test_extra_rankings_are_scored_too() -> None:
    city = make_city(size=18)
    truth = city.sites.bike_rate
    table = holdout(
        city.crashes, city.sites.index, city.streets, extra=lambda early, car: {"Truth": truth}
    )
    assert "Truth" in set(table.ranking)


def test_rank_score_is_half_for_a_constant_score() -> None:
    later = pd.Series([0, 1, 0, 2])
    assert rank_score(pd.Series([1.0] * 4), later) == pytest.approx(0.5)


def test_los_altos_config_loads() -> None:
    settings = config.load(ROOT / "config" / "los_altos.yaml")
    assert settings.city == "Los Altos" and settings.child_max_age == 18
    assert settings.holdout_windows[-1] == (2022, 2023, None)
    assert settings.ccrs_county_code == 43 and "Los Altos" in settings.ccrs_cities
    rule = settings.agency_reassignments[0]
    assert (rule.filed_as, rule.agency, rule.beat_prefix) == ("4312", "4305", "LA")
    assert settings.municipality_aliases == {"UNINCORPORATED": "SANTA CLARA COUNTY"}


def test_config_rejects_a_window_out_of_order(tmp_path: Path) -> None:
    text = (
        (ROOT / "config" / "los_altos.yaml")
        .read_text()
        .replace("[2018, 2019, 2022]", "[2019, 2019, 2022]")
    )
    bad = tmp_path / "bad.yaml"
    bad.write_text(text)
    with pytest.raises(ValueError, match="out of order"):
        config.load(bad)


def _counts(city: City, keep: float) -> tuple[pd.Series, pd.Series]:
    crashes, index = city.crashes, city.sites.index
    bikes = crashes[crashes.group != CAR].sample(frac=keep, random_state=5)
    cars = crashes[crashes.group == CAR]
    return (
        bikes.groupby("site").size().reindex(index, fill_value=0),
        cars.groupby("site").size().reindex(index, fill_value=0),
    )


def test_ranking_uses_the_model_when_there_are_enough_crashes() -> None:
    city = make_city()
    bike, car = _counts(city, 1.0)
    ranked = rank_intersections(bike, car, city.streets)
    assert ranked["method"] == "street-length model" and ranked["reason"] is None
    pd.testing.assert_series_equal(ranked["score"], ranked["fit"]["sites"].eb)


def test_ranking_falls_back_to_the_blend_when_crashes_are_few() -> None:
    city = make_city()
    bike, car = _counts(city, 0.03)
    assert 0 < bike.sum() < 100
    ranked = rank_intersections(bike, car, city.streets)
    assert ranked["method"] == "hand-built blend" and ranked["fit"] is None
    assert "fewer than 100" in ranked["reason"]
    assert ranked["score"].notna().all()
    # still far better than the bare record at finding the truly risky corners
    truth = city.sites.bike_rate
    assert (
        ranked["score"].corr(truth, method="spearman") > bike.corr(truth, method="spearman") + 0.1
    )


def test_ranking_falls_back_when_the_fit_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    from bike_safety_ca.model import crash_history

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("street crash model did not converge")

    monkeypatch.setattr(crash_history, "fit_street_model", fail)
    city = make_city(size=12)
    bike, car = _counts(city, 1.0)
    ranked = rank_intersections(bike, car, city.streets, min_crashes=1)
    assert ranked["method"] == "hand-built blend" and "did not converge" in ranked["reason"]


def test_compare_reports_matching_and_differing_tables() -> None:
    from bike_safety_ca.checks.holdout import compare

    city = make_city()
    table = holdout(city.crashes, city.sites.index, city.streets)
    assert compare(table, table.copy()) == ""
    shifted = table.assign(**{"rank score": table["rank score"] + 0.01})
    assert "rank score differs by up to 0.01" in compare(shifted, table)
    assert "rows are in only one" in compare(table.iloc[1:], table)
    twice = pd.concat([table, table.iloc[:1]])
    assert "repeated rows" in compare(twice, table) and "repeated rows" in compare(table, twice)
    assert "tested on is missing" in compare(table.drop(columns="tested on"), table)
    assert "rank score is missing" in compare(table.drop(columns="rank score"), table)
    relabelled = table.assign(**{"tested on": "2031–2032"})
    assert "tested on differs" in compare(relabelled, table)
    blank = table.assign(**{"rank score": float("nan")})
    assert "rank score is missing in one table" in compare(blank, table)
    assert compare(blank, blank.copy()) == ""


def _settings(tmp_path: Path, **changes: object) -> Path:
    import yaml

    raw = yaml.safe_load(Path("config/demo_claremont.yaml").read_text())
    for key in ("area_file", "city_limit_file", "streets_file"):
        if raw.get(key):
            raw[key] = str((Path("config") / raw[key]).resolve())
    path = tmp_path / "city.yaml"
    path.write_text(yaml.safe_dump(raw | changes))
    return path


def test_config_rejects_feet_degrees_and_a_source_that_is_not_built(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="in metres"):
        config.load(_settings(tmp_path, crs="EPSG:2227"))  # California zone 3, US feet
    with pytest.raises(ValueError, match="in metres"):
        config.load(_settings(tmp_path, crs="EPSG:4326"))
    with pytest.raises(ValueError, match="not projected"):
        config.load(_settings(tmp_path, crs="EPSG:4978"))  # metres, but from the Earth's centre
    with pytest.raises(ValueError, match="not supported yet"):
        config.load(_settings(tmp_path, crash_source="ccrs"))
    assert config.load(_settings(tmp_path, summer_break=["06-15", "08-20"])).summer_break == (
        (6, 15),
        (8, 20),
    )
    with pytest.raises(ValueError, match="summer_break"):
        config.load(_settings(tmp_path, summer_break=["08-20", "06-15"]))


def test_the_earlier_model_failing_leaves_out_its_row_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bike_safety_ca.checks import holdout as module

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("did not converge")

    monkeypatch.setattr(module, "fit_history_model", fail)
    city = make_city()
    table = holdout(city.crashes, city.sites.index, city.streets)
    assert module.EARLIER_MODEL not in set(table.ranking)
    assert module.MODEL in set(table.ranking) and table["rank score"].notna().all()


def test_age_label_puts_the_child_age_in_a_name() -> None:
    from bike_safety_ca import age_label

    assert age_label(CHILD, 15) == "Cyclist 15 or under"
    assert age_label("Cyclists 18 or under", 18) == "Cyclists 18 or under"


def test_scoring_each_city_on_its_own_makes_no_comparison_across_cities() -> None:
    import pandas as pd

    from bike_safety_ca.checks.sensitivity import within_cities
    from bike_safety_ca.model.crash_history import rank_score

    score = pd.Series([2.0, 1.0, 9.0, 8.0])
    later = pd.Series([1, 0, 0, 0])
    city = pd.Series(["A", "A", "B", "B"])
    # City A is ordered perfectly; city B has no later crash and makes no comparison.
    assert within_cities(score, later, city) == 1.0
    assert rank_score(score, later) < 1.0


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
@pytest.mark.filterwarnings("ignore::statsmodels.tools.sm_exceptions.ConvergenceWarning")
@pytest.mark.filterwarnings("ignore::statsmodels.tools.sm_exceptions.HessianInversionWarning")
def test_the_severity_table_compares_rankings_with_and_without_minor_crashes() -> None:
    import numpy as np

    from bike_safety_ca.checks import sensitivity
    from bike_safety_ca.synthetic import make_city

    city = make_city()
    streets = pd.Series(dict(city.streets))
    windows = ((2018, 2019, 2022),)
    assert (
        sensitivity.by_severity(windows, city.sites.index, streets, city.crashes) is None
    )  # no column

    # Made-up severities: every third crash a complaint of pain, a few with none recorded.
    order = np.arange(len(city.crashes))
    # The rest are visible (3), serious (2) or fatal (1) in turn.
    worse_code = np.array(["3", "2", "1"])[order % 7 % 3]
    severity = np.where(order % 3 == 0, "4", np.where(order % 50 == 1, "0", worse_code))
    hits = city.crashes.assign(COLLISION_SEVERITY=severity)
    table = sensitivity.by_severity(windows, city.sites.index, streets, hits)
    assert table is not None
    assert table.index.tolist() == [
        "Trained on all injury crashes",
        "Trained on visible injury and worse",
    ]
    cyclists = hits[hits.group.ne(sensitivity.CAR)]
    worse = cyclists[cyclists.COLLISION_SEVERITY.isin(["1", "2", "3"])]
    assert worse.COLLISION_SEVERITY.nunique() == 3
    trained = table["cyclist crashes trained on"].tolist()
    assert trained == [int(cyclists.year.le(2018).sum()), int(worse.year.le(2018).sum())]
    every, visible = (
        "Later cyclist crashes, all injury crashes",
        "Later cyclist crashes, visible injury and worse",
    )
    assert table[f"{every}: count"].tolist() == [int(cyclists.year.between(2019, 2022).sum())] * 2
    assert table[f"{visible}: count"].tolist() == [int(worse.year.between(2019, 2022).sum())] * 2
    assert table["windows scored"].tolist() == [1, 1]
    assert table["windows with a fitted model"].tolist() == [1, 1]
    assert (
        0.5
        < table[[every, visible]].to_numpy().min()
        <= table[[every, visible]].to_numpy().max()
        <= 1
    )
    assert table[every].nunique() == 2  # the two rankings are not the same ranking

    # A window with too few later crashes of either kind is left out of both columns.
    minor = ~hits.COLLISION_SEVERITY.isin(["1", "2", "3"])
    sparse = hits[hits.year.le(2018) | minor | hits.group.eq(sensitivity.CAR)]
    empty = sensitivity.by_severity(windows, city.sites.index, streets, sparse)
    assert empty is not None and empty["windows scored"].tolist() == [0, 0]
    assert empty[every].isna().all()

    # Two windows trained through the same year are told apart, and only the one with
    # enough later crashes of both kinds is counted, its training crashes once.
    late_minor = hits[~(hits.year.eq(2019) & ~minor & hits.group.ne(sensitivity.CAR))]
    two = sensitivity.by_severity(
        ((2018, 2019, 2019), (2018, 2020, 2022)), city.sites.index, streets, late_minor
    )
    assert two is not None and two["windows scored"].tolist() == [1, 1]
    assert two["cyclist crashes trained on"].tolist() == trained
    assert two[f"{every}: count"].tolist() == [int(cyclists.year.between(2020, 2022).sum())] * 2

    # With too few crashes to fit, the blend stands in and the table says so.
    few = hits[hits.group.eq(sensitivity.CAR) | (order % 40 == 0) | hits.year.gt(2018)]
    thin = sensitivity.by_severity(windows, city.sites.index, streets, few)
    assert thin is not None and thin["windows scored"].tolist() == [1, 1]
    assert thin["windows with a fitted model"].tolist() == [0, 0]
