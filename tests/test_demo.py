"""The demo city: real streets, made-up crashes, run through every step."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest

from bike_safety_ca import config, demo
from bike_safety_ca.checks import holdout, reporting
from bike_safety_ca.io import read_shapes
from bike_safety_ca.network import junctions
from bike_safety_ca.network import streets as street_table
from bike_safety_ca.report import crashes as crash_table
from bike_safety_ca.report import movement

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = config.load(ROOT / "config" / "demo_claremont.yaml")


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    return demo.build(SETTINGS, tmp_path_factory.mktemp("demo"))


def test_every_record_is_marked_synthetic(built: dict[str, Path]) -> None:
    crashes = gpd.read_parquet(built["crashes"])
    parties = pd.read_parquet(built["parties"])
    assert len(crashes) > 5000 and crashes.merged_id.is_unique
    assert crashes.merged_id.str.startswith(demo.PREFIX).all()
    assert crashes.CASE_ID.dropna().str.startswith(demo.PREFIX).all()
    assert parties.CASE_ID.str.startswith(demo.PREFIX).all()
    assert set(parties.CASE_ID) == set(crashes.merged_id)
    assert set(crashes.reporting_agency) == {"SYN-A", "SYN-B", "SYN-C"}
    assert set(crashes.CITY) == {"Claremont", demo.WEST, demo.EAST}


def test_a_cyclist_riding_the_wrong_way_has_that_cause(built: dict[str, Path]) -> None:
    crashes = gpd.read_parquet(built["crashes"])
    parties = pd.read_parquet(built["parties"])
    rider = parties[parties.PARTY_NUMBER.eq("1")].set_index("CASE_ID").MOVE_PRE_ACC
    bike = crashes[crashes.bike_involved]
    wrong_way = rider.reindex(bike.merged_id).eq("Q").to_numpy()
    assert wrong_way.any()
    # Cause 05 is also drawn at random, so only one way round holds.
    assert bike.PCF_VIOL_CATEGORY.eq("05").to_numpy()[wrong_way].all()


def test_the_same_seed_gives_the_same_crashes(built: dict[str, Path], tmp_path: Path) -> None:
    again = demo.build(SETTINGS, tmp_path)
    first, second = gpd.read_parquet(built["crashes"]), gpd.read_parquet(again["crashes"])
    pd.testing.assert_frame_equal(first.drop(columns="geometry"), second.drop(columns="geometry"))
    assert first.geometry.geom_equals(second.geometry).all()
    other = demo.build(SETTINGS, tmp_path / "other", seed=1)
    assert len(gpd.read_parquet(other["crashes"])) != len(first)


def test_build_needs_a_config_marked_synthetic(tmp_path: Path) -> None:
    real = config.load(ROOT / "config" / "los_altos.yaml")
    with pytest.raises(ValueError, match="synthetic: true"):
        demo.build(real, tmp_path)


def test_the_reporting_check_finds_what_was_planted(built: dict[str, Path]) -> None:
    reports = reporting.load(built["crashes"].parent, SETTINGS.crs, SETTINGS.first_year)
    found = reporting.diagnose(reports)
    flagged = found["injury_crashes_flags"]
    assert set(flagged.reporting_agency) == {"SYN-C"}
    # The loss is planted from April 2022, so that part-year is flagged in some draws.
    assert {2023, 2024, 2025} <= set(flagged.year) <= {2022, 2023, 2024, 2025}
    formats = found[reporting.FORMAT].groupby(level=0).sum()
    assert (formats[reporting.CCRS_FORMAT] > 0).all()  # every agency changes format
    severity = found[reporting.SEVERITY].to_dict("index")
    before, after = severity[("SYN-A", 2021)], severity[("SYN-A", 2023)]
    assert after["Complaint of pain"] < 0.4 * before["Complaint of pain"]  # regraded
    assert sum(after.values()) > 0.8 * sum(before.values())  # with the total holding


def test_the_holdout_and_the_map_run_on_the_demo(built: dict[str, Path], tmp_path: Path) -> None:
    assert SETTINGS.area_file is not None and SETTINGS.city_limit_file is not None
    folder = built["crashes"].parent
    table = holdout.city_holdout(
        SETTINGS, folder, built["streets"], SETTINGS.area_file, SETTINGS.city_limit_file
    )
    scores = table[table.outcome == "All cyclists"].groupby("ranking")["rank score"].mean()
    assert scores[holdout.MODEL] > scores["Past bike crashes"] + 0.03

    outline = read_shapes(SETTINGS.area_file).to_crs(SETTINGS.crs).union_all()
    crashes = crash_table.load(folder, SETTINGS, outline)
    parties = pd.read_parquet(built["parties"])
    page = movement.build(
        crashes, parties, gpd.read_parquet(built["streets"]), SETTINGS, tmp_path / "map.html"
    ).read_text()
    assert movement.SYNTHETIC_NOTICE[0] in page and movement.REAL_NOTICE[0] not in page


def test_the_truth_lines_up_with_the_intersections(built: dict[str, Path]) -> None:
    truth = gpd.read_parquet(built["truth"])
    assert truth.index.is_unique and (truth.bike_rate > 0).all()
    assert SETTINGS.area_file is not None
    outline = read_shapes(SETTINGS.area_file).to_crs(SETTINGS.crs).union_all()
    sites, _ = junctions.build_junctions(
        gpd.read_parquet(built["streets"], columns=street_table.COLUMNS), outline
    )
    assert list(truth.index) == list(sites.index)
    assert truth.geometry.geom_equals(sites.geometry).all()
    assert truth.bike_rate.sum() == pytest.approx(demo.BIKE_PER_YEAR * (1 - demo.MID_BLOCK_SHARE))


def test_the_walkthrough_notebook_runs_as_a_script() -> None:
    done = subprocess.run(
        [sys.executable, str(ROOT / "notebooks" / "walkthrough.py")],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert done.returncode == 0, done.stderr[-2000:]


def test_the_sensitivity_tables_run_on_the_demo_city(built: dict[str, Path]) -> None:
    from shapely.geometry import box

    from bike_safety_ca.checks import sensitivity

    assert SETTINGS.area_file is not None and SETTINGS.city_limit_file is not None
    outline = read_shapes(SETTINGS.area_file).to_crs(SETTINGS.crs).union_all()
    limit = read_shapes(SETTINGS.city_limit_file).to_crs(SETTINGS.crs).union_all()
    folder = built["crashes"].parent
    table = sensitivity.variants(SETTINGS, folder, built["streets"], outline, limit)
    assert list(table.index[:1]) == ["As configured"] and len(table) == 4
    assert table["All intersections, All cyclists"].between(0.5, 1).all()
    sites = [int(n) for n in table.intersections]
    assert sites[3] >= sites[0]  # chains split: never fewer
    assert sites[1] <= sites[0]  # wide ones left out

    # The city limit and two made-up neighbours stand in for the Census places.
    # "Strip" is the eastern quarter of the area outside the city: few
    # intersections, and the agency there files three reports in ten.
    west, south, east, north = outline.bounds
    strip = box(east - 0.25 * (east - west), south, east, north).difference(limit)
    places = gpd.GeoDataFrame(
        {"NAME": ["Claremont", "Elsewhere", "Strip"], "STATEFP": "06", "LSAD": "25"},
        geometry=[limit, box(west, south, east, north).difference(limit).difference(strip), strip],
        crs=SETTINGS.crs,
    )
    by_place = sensitivity.by_place(
        SETTINGS, folder, built["streets"], outline, limit, places, leave_out="Elsewhere"
    )
    count = {str(k): int(v) for k, v in by_place.intersections.items()}
    assert count["All intersections"] == sites[0]
    assert count["Inside the configured area"] + count["Outside it"] == sites[0]
    small = "Outside it, without Elsewhere"  # the strip alone
    assert 0 < count[small] < count["Outside it"]
    assert 0.5 < float(by_place["All cyclists"][sensitivity.WITHIN]) <= 1
    # As in the hold-out, a subset with too few later crashes keeps its count and has no score.
    # The strip has about ten later cyclist crashes, well under the floor in any draw.
    assert 0 < by_place["All cyclists: later crashes"][small] < holdout.MIN_LATER
    assert pd.isna(by_place["All cyclists"][small])
    child = "Cyclists 18 or under"
    few = by_place[f"{child}: later crashes"].lt(holdout.MIN_LATER)
    assert few[small] and not few["All intersections"]
    assert by_place[child][few].isna().all() and by_place[child][~few].between(0.5, 1).all()


def test_the_map_finds_the_patterns_planted_at_three_corners(built: dict[str, Path]) -> None:
    from bike_safety_ca.report import codes

    assert SETTINGS.area_file is not None
    outline = read_shapes(SETTINGS.area_file).to_crs(SETTINGS.crs).union_all()
    crashes = crash_table.load(built["crashes"].parent, SETTINGS, outline)
    parties = pd.read_parquet(built["parties"])
    ways = gpd.read_parquet(built["streets"])
    at, sites = movement.place(crashes, ways, outline)
    rows = pd.DataFrame(
        movement.crash_rows(movement.cyclists(crashes), parties, ways, SETTINGS.child_max_age, at)
    )
    planted = pd.read_parquet(built["truth"]).planted.dropna()
    assert sorted(planted) == sorted(demo.PLANTED)
    for site, kind in zip(planted.index.astype(int), planted, strict=True):
        here = rows[rows.si.eq(site)]
        assert len(here) >= 4, kind
        if kind == "after dark":
            assert here["lt"].isin(codes.DARK).mean() >= 0.6
            continue
        top, count = here.pk.value_counts().index[0], here.pk.value_counts().iloc[0]
        expected = "right turn, same direction" if kind == "right hook" else "left turn, opposite"
        assert expected in top and count >= 0.6 * len(here), (kind, top)
    # Movements agree with directions: a car turning right across a cyclist travels their way.
    hooks = rows.pk.str.contains("right turn, same direction").sum()
    assert hooks > 20 and set(rows["lt"]) <= {*codes.LIGHTING, ""}


def test_every_demo_crash_is_in_one_wrong_side_category_at_most(built: dict[str, Path]) -> None:
    assert SETTINGS.area_file is not None
    outline = read_shapes(SETTINGS.area_file).to_crs(SETTINGS.crs).union_all()
    crashes = crash_table.load(built["crashes"].parent, SETTINGS, outline)
    parties = pd.read_parquet(built["parties"])
    ways = gpd.read_parquet(built["streets"])
    at, sites = movement.place(crashes, ways, outline)
    legs = {s["i"]: s["w"] for s in sites}
    rows = movement.crash_rows(
        movement.cyclists(crashes), parties, ways, SETTINGS.child_max_age, at, legs
    )
    counts = {"coded": 0, "unclear": 0, "suggested": 0, "": 0}
    for row in rows:
        cited = "wrong side" in row["cause"].lower()
        coded = row["wc"]
        unclear = row["wu"]
        suggested = bool(row["ws"]) or row["fit"] == "against"
        # Coded, cited with the party unclear, and suggested by the movements only.
        in_each = [coded, unclear, suggested and not coded and not cited]
        assert sum(in_each) <= 1
        assert not (unclear and suggested)  # nothing puts a cited crash's cyclist against traffic
        assert not (coded and row["fit"] == "against")
        assert unclear == (cited and not coded)
        assert in_each == [movement.wrong_side(row) == k for k in ("coded", "unclear", "suggested")]
        counts[movement.wrong_side(row)] += 1
    assert all(counts[k] for k in ("coded", "unclear", "suggested"))  # the demo has each kind
