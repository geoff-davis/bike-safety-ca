"""The bike-route flag test, on made-up streets and crashes only."""

import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely import LineString, Point

from bike_safety_ca import CAR, CYCLISTS
from bike_safety_ca.checks import bike_routes
from bike_safety_ca.checks.bike_routes import compare, flags, main, route_ways, routes, tagged_ways
from bike_safety_ca.download import osm
from bike_safety_ca.model.crash_history import fit_street_model
from bike_safety_ca.synthetic import make_city


def _way(i: int, **tags: str) -> dict:
    return {"type": "way", "id": i, "nodes": [], "tags": tags}


def test_lanes_and_designated_streets_are_read_from_the_tags() -> None:
    raw = {
        "elements": [
            _way(1, highway="primary", cycleway="lane"),
            _way(2, highway="secondary", **{"cycleway:right": "track"}),
            _way(3, highway="residential", cycleway="no"),
            _way(4, highway="residential", bicycle="designated"),
            _way(5, highway="cycleway", bicycle="designated"),  # a path, not a street
            _way(6, highway="residential", cyclestreet="yes"),
            {"type": "node", "id": 7, "lat": 0, "lon": 0},
        ]
    }
    assert tagged_ways(raw) == ({1, 2}, {4, 6})


def test_the_ways_of_bike_route_relations_are_collected() -> None:
    relations = {
        "elements": [
            {
                "type": "relation",
                "members": [{"type": "way", "ref": 1}, {"type": "node", "ref": 2}],
            },
            {"type": "relation", "members": [{"type": "way", "ref": 3}]},
        ]
    }
    assert route_ways(relations) == {1, 3}


def test_each_corner_takes_the_group_of_the_streets_beside_it() -> None:
    sites = gpd.GeoSeries([Point(0, 0), Point(100, 0), Point(200, 0), Point(300, 0)])
    ways = gpd.GeoDataFrame(
        {"osm_id": [1, 2, 3]},
        geometry=[
            LineString([(-10, 15), (10, 15)]),  # 15 m from the first corner: a lane
            LineString([(90, -5), (110, -5)]),  # beside the second: a route
            LineString([(190, 5), (210, 5)]),  # the third: both, so a lane
        ],
    )
    group = flags(sites, ways, lane={1, 3}, route={2, 3})
    assert group.tolist() == ["lane", "route, no lane", "lane", "neither"]
    assert flags(sites, ways, lane=set(), route=set()).eq("neither").all()


def test_extra_columns_enter_the_fit_and_leave_the_plain_fit_alone() -> None:
    city = make_city()
    bike = city.crashes[city.crashes.group.isin(CYCLISTS)].groupby("site").size()
    bike = bike.reindex(city.sites.index, fill_value=0)
    car = city.crashes[city.crashes.group == CAR].groupby("site").size()
    car = car.reindex(city.sites.index, fill_value=0)
    plain = fit_street_model(bike, car, city.streets)
    flag = pd.DataFrame({"flag": (np.arange(len(bike)) % 3 == 0).astype(float)}, index=bike.index)
    flagged = fit_street_model(bike, car, city.streets, extra=flag)
    assert list(plain["powers"].index) == ["street_bike", "car"]
    assert list(flagged["powers"].index) == ["street_bike", "car", "flag"]
    # Nested fits: the extra term can only raise the likelihood (up to the optimiser).
    assert flagged["log_likelihood"] >= plain["log_likelihood"] - 1e-3


def test_each_window_of_the_synthetic_city_is_compared() -> None:
    city = make_city()
    group = pd.Series("neither", index=city.sites.index)
    group.iloc[::5] = "lane"  # no "route, no lane": that flag is left out of the fit
    table = compare(city.crashes, city.sites.index, city.streets, group)
    assert len(table) == 3
    fitted = table[table.method == "street-length model"]
    assert fitted["rank score, flags"].between(0.5, 1).all()
    assert fitted["p, flags"].between(0, 1).all()
    assert "multiplier, route, no lane" not in table
    assert "later / expected, route, no lane" not in table
    # Over all groups, later crashes match the scaled expectation by construction.
    assert fitted["later / expected, lane"].gt(0).all()


def _saved_download(folder: Path, box: list[float]) -> Path:
    raw = folder / "overpass_streets.json"
    raw.write_text("{}")
    note = folder / "overpass_streets.metadata.json"
    note.write_text(json.dumps({"bounds_west_south_east_north": box}))
    return raw


def test_the_route_relations_are_fetched_once_for_the_download_box(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    box = [-117.6, 34.4, -117.4, 34.6]
    raw = _saved_download(tmp_path, box)
    asked = []

    def run(query: str, require_elements: bool = True) -> dict:
        asked.append((query, require_elements))
        return {"elements": []}  # a city may have no route relations

    monkeypatch.setattr(osm, "run", run)
    out = tmp_path / "overpass_bike_routes.json"
    first = routes(raw, out)
    ((query, required),) = asked
    assert '"route"="bicycle"](34.4,-117.6,34.6,-117.4)' in query and not required
    assert first["bounds_west_south_east_north"] == box
    assert routes(raw, out) == first and len(asked) == 1  # read back, not fetched again
    _saved_download(tmp_path, [-117.3, 34.4, -117.2, 34.5])  # the streets were fetched anew
    with pytest.raises(ValueError, match="another box"):
        routes(raw, out)
    routes(raw, out, overwrite=True)
    assert len(asked) == 2


def test_an_empty_answer_passes_only_when_allowed() -> None:
    osm.check({"elements": []}, require_elements=False)
    with pytest.raises(ValueError, match="no streets"):
        osm.check({"elements": []})
    with pytest.raises(ValueError, match="did not finish"):
        osm.check({"elements": [], "remark": "timed out"}, require_elements=False)


def test_the_command_runs_on_the_synthetic_city(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "table.csv"
    monkeypatch.setattr(sys, "argv", ["bike_routes", "--synthetic", "--out", str(out)])
    main()
    printed = capsys.readouterr().out
    assert "made-up flags" in printed and "Share of intersections" in printed
    assert len(pd.read_csv(out)) == 3
    monkeypatch.setattr(sys, "argv", ["bike_routes"])
    with pytest.raises(SystemExit):
        bike_routes.main()


def test_without_a_neither_group_one_flag_is_fitted_against_the_other() -> None:
    city = make_city()
    group = pd.Series("route, no lane", index=city.sites.index)
    group.iloc[::4] = "lane"  # every corner is on a lane or a route: no "neither"
    table = compare(city.crashes, city.sites.index, city.streets, group)
    fitted = table[table.method == "street-length model"]
    assert len(fitted) > 0
    assert (fitted["reference group"] == "route, no lane").all()
    # One column, not two that add up to the intercept.
    assert fitted["multiplier, lane"].notna().all()
    assert "multiplier, route, no lane" not in table
    assert fitted["p, flags"].between(0, 1).all()


def test_the_reference_is_neither_when_any_corner_has_it() -> None:
    city = make_city()
    group = pd.Series("neither", index=city.sites.index)
    group.iloc[::5], group.iloc[1::7] = "lane", "route, no lane"
    table = compare(city.crashes, city.sites.index, city.streets, group)
    assert (table["reference group"] == "neither").all()
    fitted = table[table.method == "street-length model"]
    assert fitted[["multiplier, lane", "multiplier, route, no lane"]].notna().all().all()
