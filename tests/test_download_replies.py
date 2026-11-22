"""A reply that is not the whole thing asked for is refused and never saved.

Every reply here is made up; nothing is fetched.
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from bike_safety_ca.download import arcgis, census, osm

BOUNDS = (-117.75, 34.08, -117.69, 34.14)
STREETS = {
    "elements": [
        {"type": "way", "id": 1, "nodes": [10, 11], "tags": {"highway": "residential"}},
        {"type": "node", "id": 10, "lon": -117.7, "lat": 34.1},
        {"type": "node", "id": 11, "lon": -117.71, "lat": 34.1},
    ]
}
TIMED_OUT = {
    "version": 0.6,
    "osm3s": {},
    "elements": STREETS["elements"][:2],  # cut short: the way's second node never arrived
    "remark": 'runtime error: Query timed out in "query" at line 2 after 601 seconds.',
}


class _Reply:
    def __init__(self, body: object) -> None:
        self.body = body
        self.text = body if isinstance(body, str) else json.dumps(body)

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return json.loads(self.text)


class _Overpass:
    """A stand-in for the Overpass servers that answers every query with ``body``."""

    def __init__(self, body: object) -> None:
        self.body, self.asked = body, 0

    def __call__(self, **kwargs: object) -> _Overpass:
        return self

    def __enter__(self) -> _Overpass:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def post(self, url: str, **kwargs: object) -> _Reply:
        self.asked += 1
        return _Reply(self.body)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (TIMED_OUT, "did not finish the query .*Query timed out"),
        ({"version": 0.6, "elements": []}, "returned no streets"),
    ],
)
def test_an_overpass_reply_that_is_cut_short_or_empty_is_not_saved(
    body: dict[str, object], message: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = _Overpass(body)
    monkeypatch.setattr(osm.httpx, "Client", server)
    monkeypatch.setattr(osm.run.retry, "sleep", lambda seconds: None)
    with pytest.raises(RuntimeError, match=message):
        osm.download(BOUNDS, tmp_path)
    assert server.asked == 4 * len(osm.OVERPASS)  # both servers, every retry
    assert list(tmp_path.iterdir()) == []  # so the next run asks again


def test_a_whole_overpass_reply_is_saved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(osm.httpx, "Client", _Overpass(STREETS))
    saved = osm.download(BOUNDS, tmp_path)
    assert json.loads(saved.read_text()) == STREETS
    assert json.loads((tmp_path / "overpass_streets.metadata.json").read_text())["elements"] == 3


SQUARE = {
    "type": "Feature",
    "properties": {"NAME": "Made Up"},
    "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]},
}
LAYER = "https://example.org/made-up/limit/0"


def _layer(monkeypatch: pytest.MonkeyPatch, body: object) -> list[str]:
    asked: list[str] = []

    def get(url: str, **kwargs: object) -> _Reply:
        asked.append(url)
        return _Reply(body)

    monkeypatch.setattr(arcgis.httpx, "get", get)
    return asked


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"type": "FeatureCollection", "features": []}, "no polygon features"),
        (
            {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": None}]},
            "no polygon features",
        ),
        (
            {"type": "FeatureCollection", "features": [SQUARE], "exceededTransferLimit": True},
            "exceededTransferLimit",
        ),
        (
            {
                "type": "FeatureCollection",
                "features": [SQUARE],
                "properties": {"exceededTransferLimit": True},
            },
            "exceededTransferLimit",
        ),
        (
            {
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []}},
                    {"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": [[]]}},
                    {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[0, 0]]]}},
                    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}},
                ],
            },
            "the layer is empty: no polygon features",
        ),
        ({"error": {"code": 400, "message": "Invalid made-up query"}}, "Invalid made-up query"),
        ('<html>the word "features" in a page</html>', "is not JSON"),
    ],
)
def test_a_layer_that_is_empty_cut_short_or_an_error_is_not_saved(
    body: object, message: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = _layer(monkeypatch, body)
    with pytest.raises(arcgis.FetchError, match=message) as refusal:
        arcgis.download(LAYER, tmp_path / "limit.geojson")
    assert LAYER in str(refusal.value)
    assert asked == [f"{LAYER}/query"]  # asking again would give the same answer
    assert list(tmp_path.iterdir()) == []


def test_a_whole_layer_is_saved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    body = {"type": "FeatureCollection", "features": [SQUARE], "exceededTransferLimit": False}
    _layer(monkeypatch, body)
    saved = arcgis.download(LAYER, tmp_path / "limit.geojson")
    assert json.loads(saved.read_text()) == body
    assert (tmp_path / "limit.geojson.source.txt").read_text() == LAYER + "\n"


def _zip(*names: str) -> bytes:
    held = io.BytesIO()
    with zipfile.ZipFile(held, "w") as archive:
        for name in names:
            archive.writestr(name, "made up")
    return held.getvalue()


class _Download:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> _Download:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    def iter_bytes(self) -> Iterator[bytes]:
        yield self.body[:10]
        yield self.body[10:]


class _Dropped(_Download):
    """A connection that sends the start of the file and then fails."""

    def iter_bytes(self) -> Iterator[bytes]:
        yield self.body[:10]
        raise httpx.ReadError("the made-up connection dropped")


def test_a_census_download_cut_off_part_way_leaves_no_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = _zip("places.shp", "places.dbf")
    monkeypatch.setattr(census.httpx, "stream", lambda method, url, **kwargs: _Dropped(body))
    monkeypatch.setattr(census._fetch.retry, "sleep", lambda seconds: None)
    with pytest.raises(httpx.ReadError, match="connection dropped"):
        census.download(tmp_path)
    assert list(tmp_path.iterdir()) == []  # no .zip.part either


@pytest.mark.parametrize(
    "body",
    [
        b"<html>Service unavailable; made-up maintenance page</html>",
        _zip("readme.txt"),  # a zip, but with no shapefile in it
        _zip("places.shp", "places.dbf")[:60],  # cut short
    ],
    ids=["a web page", "no shapefile", "cut short"],
)
def test_a_census_reply_that_is_not_a_boundary_zip_is_not_saved(
    body: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []

    def stream(method: str, url: str, **kwargs: object) -> _Download:
        asked.append(url)
        return _Download(body)

    monkeypatch.setattr(census.httpx, "stream", stream)
    monkeypatch.setattr(census._fetch.retry, "sleep", lambda seconds: None)
    with pytest.raises(ValueError, match="is not a zip file holding a shapefile"):
        census.download(tmp_path)
    assert len(asked) == 4  # the first file, retried; the second is never reached
    assert list(tmp_path.iterdir()) == []  # nothing a later run would take as downloaded


def test_a_census_boundary_zip_is_saved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    body = _zip("places.shp", "places.dbf")
    monkeypatch.setattr(census.httpx, "stream", lambda method, url, **kwargs: _Download(body))
    paths = census.download(tmp_path)
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted(
        f"{name}.zip" for name in census.names().values()
    )
    assert all(path.read_bytes() == body for path in paths.values())
