"""A config value that would silently change results is refused when the file is loaded."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bike_safety_ca import config

ROOT = Path(__file__).resolve().parents[1]
SETTINGS: dict[str, object] = {
    "city": "Alder",
    "county": "Made Up",
    "crash_source": "tims+ccrs",
    "first_year": 2014,
    "child_max_age": 15,
    "holdout_windows": [[2018, 2019, 2022], [2022, 2023, None]],
    "crs": "EPSG:26910",
    "ccrs_county_code": 99,
    "ccrs_cities": ["Alder", "Birch"],
    "latitude": [36.9, 37.1],
    "longitude": [-122.1, -121.9],
}


RULE: dict[str, object] = {"filed_as": "0102", "agency": "0101", "beat_prefix": "AL"}
POINTS: dict[str, object] = {"area_points": [[-122.0, 37.0]], "area_buffer_m": 100.0}


def _settings(folder: Path, text: str = "", **changes: object) -> Path:
    path = folder / "alder.yaml"
    path.write_text(yaml.safe_dump(SETTINGS | changes) + text)
    return path


@pytest.mark.parametrize("path", sorted((ROOT / "config").glob("*.yaml")), ids=lambda p: p.stem)
def test_every_config_in_the_repository_loads(path: Path) -> None:
    assert config.load(path).city


def test_the_made_up_config_loads(tmp_path: Path) -> None:
    assert config.load(_settings(tmp_path)).ccrs_cities == ("Alder", "Birch")


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("latitude", [37.1, 36.9], "low first"),  # reversed
        ("latitude", [37.0, 37.0], "low first"),
        ("latitude", [-122.1, -121.9], "between -90 and 90"),  # longitude's values
        ("longitude", [-121.9, -122.1], "low first"),
        ("longitude", [-200.0, -121.9], "between -180 and 180"),
        ("longitude", [-122.1], "low first"),
        ("longitude", ["west", "east"], "low first"),
        ("ccrs_cities", "Alder", "list of city names"),
        ("ccrs_cities", [], "list of city names"),
        ("ccrs_cities", ["Alder", 7], "list of city names"),
        ("first_year", 2014.5, "whole year from 1990 to 2100"),
        ("first_year", 20140, "whole year from 1990 to 2100"),
        ("first_year", "2014", "whole year from 1990 to 2100"),
        ("first_year", True, "whole year from 1990 to 2100"),
        ("holdout_windows", [[2018, 2019]], "each window is"),
        ("holdout_windows", [[2018, 20190, None]], "each window is"),
        ("holdout_windows", [[2018, "2019", None]], "each window is"),
        ("holdout_windows", [[2018, 2019, 2018]], "out of order"),
        ("holdout_windows", [[2019, 2019, None]], "out of order"),
        ("holdout_windows", 2018, "each window is"),
        ("child_max_age", -3, "from 0 to 120"),
        ("child_max_age", "eighteen", "from 0 to 120"),
        ("child_max_age", 17.5, "from 0 to 120"),
        ("child_max_age", 180, "from 0 to 120"),
        ("osm_date", "22 August 2031", "in quotes"),
        ("osm_date", '2031"];node(1);out;[', "in quotes"),
        ("osm_date", "2031-02-30T00:00:00Z", "not a real date"),
        ("osm_date", 2031, "in quotes"),
        ("area_buffer_m", -1, "0 or more"),
        ("area_buffer_m", float("inf"), "0 or more"),
        ("area_buffer_m", float("nan"), "0 or more"),
        ("area_buffer_m", "two miles", "0 or more"),
        ("area_buffer_m", True, "0 or more"),
        ("agency_reassignments", [RULE | {"from_year": 2023.9}], "from_year must be a whole year"),
        ("agency_reassignments", [RULE | {"from_year": "2023"}], "from_year must be a whole year"),
        ("agency_reassignments", [RULE | {"from_year": 20230}], "from_year must be a whole year"),
        ("ccrs_county_code", "Made Up", "whole number from 1 to 99"),
        ("ccrs_county_code", 19.5, "whole number from 1 to 99"),
        ("ccrs_county_code", 0, "whole number from 1 to 99"),
        ("ccrs_county_code", 190, "whole number from 1 to 99"),
        ("synthetic", "false", "true or false, without quotes"),
        ("synthetic", 1, "true or false, without quotes"),
        ("summer_break", ["13-45", "14-99"], "first day then last"),
        ("summer_break", ["02-30", "08-14"], "first day then last"),
        ("summer_break", ["08-14", "06-08"], "first day then last"),
        ("summer_break", ["06-08"], "first day then last"),
        ("summer_break", ["June 8", "Aug 14"], "first day then last"),
        ("summer_break", "06-08", "first day then last"),
    ],
)
def test_a_value_that_would_change_results_is_refused(
    key: str, value: object, message: str, tmp_path: Path
) -> None:
    path = tmp_path / "alder.yaml"
    path.write_text(yaml.safe_dump(SETTINGS | POINTS | {key: value}))
    with pytest.raises(ValueError, match=message) as refusal:
        config.load(path)
    # The message says which key to fix, and in which file.
    assert str(refusal.value).startswith(f"{path}: {key}: ")


def test_the_optional_values_load_in_their_expected_forms(tmp_path: Path) -> None:
    loaded = config.load(
        _settings(
            tmp_path,
            area_points=[[-122.0, 37.0]],
            area_buffer_m=0,
            agency_reassignments=[RULE | {"from_year": 2023}],
            synthetic=True,
            summer_break=["02-29", "08-14"],
        )
    )
    assert loaded.area_buffer_m == 0 and loaded.synthetic is True
    assert loaded.agency_reassignments[0].from_year == 2023
    assert loaded.summer_break == ((2, 29), (8, 14))


def test_a_first_year_after_the_training_years_is_refused(tmp_path: Path) -> None:
    path = _settings(tmp_path, first_year=2019)
    with pytest.raises(ValueError, match=r"out of order \(first_year is 2019\)") as refusal:
        config.load(path)
    assert str(refusal.value).startswith(f"{path}: holdout_windows: ")


def test_an_unquoted_map_date_is_put_back_in_overpass_form(tmp_path: Path) -> None:
    quoted = _settings(tmp_path, osm_date="2031-01-02T03:04:05Z")
    assert config.load(quoted).osm_date == "2031-01-02T03:04:05Z"
    # YAML reads an unquoted time as a time, not as text.
    for written, kept in [
        ("2031-01-02T03:04:05Z", "2031-01-02T03:04:05Z"),
        ("2031-01-02 03:04:05", "2031-01-02T03:04:05Z"),
        ("2031-01-02T03:04:05-08:00", "2031-01-02T11:04:05Z"),
    ]:
        assert config.load(_settings(tmp_path, f"osm_date: {written}\n")).osm_date == kept
    path = _settings(tmp_path, "osm_date: 2031-01-02\n")  # a day, with no time
    with pytest.raises(ValueError, match="in quotes.*no time of day") as refusal:
        config.load(path)
    assert str(refusal.value).startswith(f"{path}: osm_date: ")


def test_unknown_and_missing_keys_are_refused(tmp_path: Path) -> None:
    path = _settings(tmp_path, frist_year=2014)
    with pytest.raises(ValueError, match="unknown key frist_year") as refusal:
        config.load(path)
    assert str(path) in str(refusal.value)
    rule = {"filed_as": "0102", "agency": "0101", "beat_prefx": "AL"}
    with pytest.raises(ValueError, match="agency_reassignments: unknown key beat_prefx"):
        config.load(_settings(tmp_path, agency_reassignments=[rule]))
    school = {"school": "Tapir Elementary", "distrct": "Made Up Unified"}
    with pytest.raises(ValueError, match="area_schools: unknown key distrct"):
        config.load(_settings(tmp_path, area_schools=[school], area_buffer_m=100.0))
    path.write_text(yaml.safe_dump({k: v for k, v in SETTINGS.items() if k != "latitude"}))
    with pytest.raises(ValueError, match="latitude: this key is required") as refusal:
        config.load(path)
    assert str(path) in str(refusal.value)
    path.write_text("")
    with pytest.raises(ValueError, match="must be a list of `key: value` settings") as refusal:
        config.load(path)
    assert str(path) in str(refusal.value)
