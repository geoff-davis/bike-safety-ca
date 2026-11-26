from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, box

from bike_safety_ca import config as settings
from bike_safety_ca.download import schools
from bike_safety_ca.network import area

CONFIG = replace(
    settings.load(Path("tests/study_area_config.yaml")),
    city="Alder",
    county="Made Up",
    ccrs_cities=("Alder", "Birch", "Unincorporated"),
    crs="EPSG:26910",
)


def _layer(rows: list[tuple[str, str, str, tuple[float, float, float, float]]]) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "NAME": [r[0] for r in rows],
            "LSAD": [r[1] for r in rows],
            "STATEFP": [r[2] for r in rows],
        },
        geometry=[box(*r[3]) for r in rows],
        crs=26910,
    )


PLACES = _layer(
    [
        ("Alder", "25", "06", (0, 0, 1000, 1000)),
        ("Birch", "43", "06", (2000, 0, 3000, 1000)),
        ("Cedar", "25", "06", (1200, 0, 1800, 400)),  # a city not on the list
        ("Dogwood", "57", "06", (1200, 500, 1800, 900)),  # a census-designated place
        ("Alder", "25", "41", (9000, 9000, 9500, 9500)),  # same name, another state
        (
            "San Elder (Elder)",
            "25",
            "06",
            (4000, 0, 5000, 1000),
        ),  # formal name, everyday in brackets
    ]
)
COUNTIES = _layer([("Made Up", "06", "06", (-5000, -5000, 8000, 6000))])


def test_area_is_the_listed_cities_and_the_open_land_between_them() -> None:
    outline, limit = area.outlines(PLACES, COUNTIES, CONFIG)
    # Two cities of 1 km2, plus the 1 km gap between them less the unlisted city.
    assert outline.area.iloc[0] == pytest.approx(3_000_000 - 600 * 400)
    assert limit.area.iloc[0] == pytest.approx(1_000_000)
    assert limit.name.tolist() == ["Alder"]


def test_without_unincorporated_the_area_is_only_the_cities() -> None:
    config = replace(CONFIG, ccrs_cities=("Alder", "Birch"))
    outline, _ = area.outlines(PLACES, COUNTIES, config)
    assert outline.area.iloc[0] == pytest.approx(2_000_000)


def test_an_unknown_city_is_an_error() -> None:
    with pytest.raises(ValueError, match="ELM"):
        area.outlines(PLACES, COUNTIES, replace(CONFIG, ccrs_cities=("Alder", "Elm")))


def test_an_unknown_city_names_the_closest_census_places() -> None:
    with pytest.raises(
        ValueError, match=r"no Census place named: ALDR \(closest: ALDER, ELDER, SAN ELDER\)"
    ):
        area.outlines(PLACES, COUNTIES, replace(CONFIG, ccrs_cities=("Aldr",)))


@pytest.mark.parametrize("written", ["Elder", "San Elder", "San Elder (Elder)"])
def test_a_city_the_census_names_with_brackets_is_found_by_any_of_its_names(written: str) -> None:
    config = replace(CONFIG, city=written, ccrs_cities=(written, "Alder"))
    outline, limit = area.outlines(PLACES, COUNTIES, config)
    assert outline.area.iloc[0] == pytest.approx(2_000_000)
    assert limit.total_bounds.tolist() == [4000, 0, 5000, 1000]


def test_incorporated_places_carry_the_name_crash_reports_use() -> None:
    cities = area.incorporated(PLACES)
    # California's cities and towns only, the bracketed one under its everyday name.
    assert cities.NAME.tolist() == ["Alder", "Birch", "Cedar", "Elder"]
    assert cities.formal.tolist() == ["Alder", "Birch", "Cedar", "San Elder"]
    assert cities.census_name.iloc[-1] == "San Elder (Elder)"
    assert PLACES.NAME.iloc[-1] == "San Elder (Elder)"  # the caller's layer is left alone


def test_the_callers_area_wins_and_drops_the_built_city_limit() -> None:
    built = area.paths(Path("out"), CONFIG.crs)
    assert area.chosen(CONFIG, Path("out")) == built
    own = area.chosen(CONFIG, Path("out"), Path("mine.geojson"))
    assert own == {"area": Path("mine.geojson"), "city_limit": None}


def test_area_around_points_joins_circles_with_the_city_limit() -> None:
    limit = gpd.GeoDataFrame(geometry=[box(0, 0, 10, 10)], crs=26910).to_crs(4326)
    spot = gpd.GeoSeries([Point(5000, 5000)], crs=26910).to_crs(4326)
    points = pd.DataFrame({"longitude": spot.x, "latitude": spot.y})
    outline = area.around_points(points, 1000.0, limit, "EPSG:26910")
    assert outline.area.iloc[0] == pytest.approx(math.pi * 1000**2 + 100, rel=0.01)


def test_the_case_study_config_asks_for_school_circles() -> None:
    config = settings.load(Path("tests/study_area_config.yaml"))
    assert config.area_buffer_m == pytest.approx(3218.688)
    assert len(config.area_schools) == 18 and len(config.area_points) == 1
    assert ("Almond Elementary", "Los Altos Elementary") in config.area_schools
    assert config.city_limit_url is not None and config.area_file is None


# A made-up school directory in the state file's layout.
DIRECTORY = (
    "CDSCode\tStatusType\tDistrict\tSchool\tLatitude\tLongitude\n"
    "1\tActive\tAlder Unified\tBirch Elementary\t37.5\t-122.5\n"
    "2\tClosed\tAlder Unified\tBirch Elementary\t37.4\t-122.4\n"
    "3\tActive\tCedar Union\tBirch Elementary\t37.3\t-122.3\n"
)


def test_schools_are_placed_from_the_directory(tmp_path: Path) -> None:
    directory = tmp_path / "pubschls.txt"
    directory.write_text(DIRECTORY, encoding="latin-1")
    config = replace(
        CONFIG,
        area_schools=(("Birch Elementary", "Alder Unified"),),
        area_points=((-122.1, 37.1),),
        area_buffer_m=100.0,
    )
    points = area.centres(config, directory)
    assert points.values.tolist() == [[-122.1, 37.1], [-122.5, 37.5]]
    with pytest.raises(ValueError, match="0 active schools"):
        schools.locate(directory, (("Elm High", "Alder Unified"),))
    with pytest.raises(ValueError, match="needs the state school directory"):
        area.centres(config)
