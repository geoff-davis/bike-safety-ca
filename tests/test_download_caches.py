"""Saved downloads are reused only for the request they were fetched for."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bike_safety_ca import config
from bike_safety_ca.download import arcgis, ccrs, osm

ROOT = Path(__file__).resolve().parents[1]


def test_streets_saved_for_another_area_are_not_reused(tmp_path: Path) -> None:
    box = osm.padded((-117.75, 34.08, -117.69, 34.14))
    (tmp_path / "overpass_streets.json").write_text('{"elements": []}')
    # With no record of its area the file is used as it is; nothing is fetched.
    assert osm.download((-122.2, 37.3, -122.0, 37.4), tmp_path).exists()
    note = {"bounds_west_south_east_north": list(box), "map_as_of": "latest"}
    (tmp_path / "overpass_streets.metadata.json").write_text(json.dumps(note))
    same = osm.download((-117.75, 34.08, -117.69, 34.14), tmp_path)  # reused, nothing fetched
    assert same == tmp_path / "overpass_streets.json"
    with pytest.raises(ValueError, match="another area or map date"):
        osm.download((-122.2, 37.3, -122.0, 37.4), tmp_path)
    with pytest.raises(ValueError, match="another area or map date"):
        osm.download((-117.75, 34.08, -117.69, 34.14), tmp_path, date="2024-01-01T00:00:00Z")


def test_a_layer_saved_from_another_address_is_not_reused(tmp_path: Path) -> None:
    dest = tmp_path / "limit.geojson"
    dest.write_text('{"features": []}')
    assert arcgis.download("https://example.org/a/0", dest) == dest  # no record: kept as before
    (tmp_path / "limit.geojson.source.txt").write_text("https://example.org/a/0\n")
    assert arcgis.download("https://example.org/a/0", dest) == dest
    with pytest.raises(ValueError, match="was fetched from"):
        arcgis.download("https://example.org/b/0", dest)


def test_crash_files_saved_for_other_cities_are_not_reused(tmp_path: Path) -> None:
    settings = config.load(ROOT / "config" / "los_altos.yaml")
    manifest = {"filter": {"County Code": "19", "City Name": ["Claremont"]}, "files": {}}
    (tmp_path / "ccrs_manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="holds CCRS files fetched for"):
        ccrs.download(settings, tmp_path)


class _Stream:
    def __init__(self, text: str) -> None:
        self.text = text

    def __enter__(self) -> _Stream:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    def iter_lines(self) -> list[str]:
        return self.text.splitlines()


class _Portal:
    """A stand-in for data.ca.gov in which no file is loaded into the datastore."""

    FILES = {
        "crashes": "\ufeffCollision Id,County Code,City Name\n1,19,Claremont\n2,19,Pomona\n3,43,Claremont\n",
        "parties": "CollisionId,PartyNumber\n1,1\n1,2\n2,1\n",
        "injured": "CollisionId,Age\n2,30\n",
    }

    def __init__(self) -> None:
        self.asked: list[str] = []

    def __enter__(self) -> _Portal:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def stream(self, method: str, url: str, **kwargs: object) -> _Stream:
        self.asked.append(url)
        return _Stream(self.FILES[url])


def test_files_not_in_the_datastore_are_streamed_and_filtered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    portal = _Portal()
    found = {
        ("Crashes", 2024): {"id": "c", "name": "Crashes_2024", "url": "crashes"},
        ("Parties", 2024): {"id": "p", "name": "Parties_2024", "url": "parties"},
        ("InjuredWitnessPassengers", 2024): {"id": "i", "name": "Injured_2024", "url": "injured"},
    }
    monkeypatch.setattr(ccrs.httpx, "Client", lambda **kwargs: portal)
    monkeypatch.setattr(ccrs, "resources", lambda client: found)

    def no_sql(*args: object, **kwargs: object) -> None:
        raise AssertionError("the datastore must not be asked")

    monkeypatch.setattr(ccrs, "fetch_table", no_sql)
    settings = config.load("config/demo_claremont.yaml")
    ccrs.download(settings, tmp_path)
    lines = {
        name: (tmp_path / name).read_text().splitlines()
        for name in ("Crashes_2024.csv", "Parties_2024.csv", "InjuredWitnessPassengers_2024.csv")
    }
    assert lines["Crashes_2024.csv"] == ["Collision Id,County Code,City Name", "1,19,Claremont"]
    assert lines["Parties_2024.csv"] == ["CollisionId,PartyNumber", "1,1", "1,2"]
    assert lines["InjuredWitnessPassengers_2024.csv"] == []
    assert portal.asked == ["crashes", "parties", "injured"]  # the crash file is read once


def test_party_files_are_fetched_again_when_the_crash_file_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    portal = _Portal()
    found = {
        ("Crashes", 2024): {
            "id": "c",
            "name": "Crashes_2024",
            "url": "crashes",
            "last_modified": "day 1",
        },
        ("Parties", 2024): {
            "id": "p",
            "name": "Parties_2024",
            "url": "parties",
            "last_modified": "day 1",
        },
    }
    monkeypatch.setattr(ccrs.httpx, "Client", lambda **kwargs: portal)
    monkeypatch.setattr(ccrs, "resources", lambda client: found)
    settings = config.load("config/demo_claremont.yaml")
    ccrs.download(settings, tmp_path)
    ccrs.download(settings, tmp_path)
    assert portal.asked == ["crashes", "parties"]  # nothing changed: nothing fetched again
    found[("Crashes", 2024)]["last_modified"] = "day 2"  # the party file's date is unchanged
    ccrs.download(settings, tmp_path)
    assert portal.asked == ["crashes", "parties", "crashes", "parties"]
    # A manifest saved before the crash file's date was recorded is not trusted either.
    manifest = next(tmp_path.glob("*.json"))
    saved = json.loads(manifest.read_text())
    del saved["files"]["Parties_2024.csv"]["crash_resource_last_modified"]
    manifest.write_text(json.dumps(saved))
    ccrs.download(settings, tmp_path)
    assert portal.asked[-1] == "parties" and len(portal.asked) == 5


def test_an_interrupted_download_leaves_a_list_of_the_files_it_wrote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    portal = _Portal()
    found = {
        ("Crashes", 2023): {"id": "c", "name": "Crashes_2023", "url": "crashes"},
        ("Crashes", 2024): {"id": "d", "name": "Crashes_2024", "url": "not there"},
    }
    monkeypatch.setattr(ccrs.httpx, "Client", lambda **kwargs: portal)
    monkeypatch.setattr(ccrs, "resources", lambda client: found)
    settings = config.load("config/demo_claremont.yaml")
    with pytest.raises(KeyError, match="not there"):
        ccrs.download(settings, tmp_path)
    saved = json.loads((tmp_path / "ccrs_manifest.json").read_text())
    assert list(saved["files"]) == ["Crashes_2023.csv"] and saved["complete"] is False
    assert saved["filter"]["City Name"] == list(settings.ccrs_cities)
    found[("Crashes", 2024)]["url"] = "crashes"
    ccrs.download(settings, tmp_path)
    saved = json.loads((tmp_path / "ccrs_manifest.json").read_text())
    assert list(saved["files"]) == ["Crashes_2023.csv", "Crashes_2024.csv"]
    assert saved["complete"] is True
    assert portal.asked == ["crashes", "not there", "crashes"]  # 2023 was not fetched again


def test_a_rerun_that_fails_on_a_new_file_leaves_the_list_marked_unfinished(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from bike_safety_ca.crashes import merge

    portal = _Portal()
    found = {("Crashes", 2023): {"id": "c", "name": "Crashes_2023", "url": "crashes"}}
    monkeypatch.setattr(ccrs.httpx, "Client", lambda **kwargs: portal)
    monkeypatch.setattr(ccrs, "resources", lambda client: found)
    settings = config.load("config/demo_claremont.yaml")
    ccrs.download(settings, tmp_path)
    assert json.loads((tmp_path / "ccrs_manifest.json").read_text())["complete"] is True
    # A new year is published; 2023 is reused from the saved copy, and the new file fails.
    found[("Crashes", 2024)] = {"id": "d", "name": "Crashes_2024", "url": "not there"}
    with pytest.raises(KeyError, match="not there"):
        ccrs.download(settings, tmp_path)
    saved = json.loads((tmp_path / "ccrs_manifest.json").read_text())
    assert saved["complete"] is False and list(saved["files"]) == ["Crashes_2023.csv"]
    with caplog.at_level("WARNING"):
        assert merge.manifest_files(tmp_path, settings) == {"Crashes_2023.csv"}
    assert "did not finish" in caplog.text
