"""Streets cut from a made-up OpenStreetMap extract."""

import json
from pathlib import Path

import geopandas as gpd
import pytest

from bike_safety_ca.download import osm
from bike_safety_ca.download.osm_extract import cut, read
from bike_safety_ca.network import streets

# The extract covers (-118.0, 34.0) to (-117.0, 35.0).  Boxes are padded by
# osm.PAD_DEG (0.01), so the bounds below give the box (-117.6, 34.4, -117.4, 34.6).
BOUNDS = (-117.59, 34.41, -117.41, 34.59)
META = 'version="3" timestamp="2026-01-02T03:04:05Z" changeset="9" uid="7" user="someone"'
NODES = {
    1: (-117.50, 34.50),  # inside the box
    2: (-117.45, 34.50),  # inside
    3: (-117.70, 34.50),  # west of the box
    4: (-117.30, 34.50),  # east of it
    5: (-117.70, 34.70),  # far outside
    6: (-117.69, 34.70),
    7: (-117.70, 34.55),  # 7 to 8 passes the box's north-west corner without touching it
    8: (-117.55, 34.70),
}


def _extract(
    path: Path, bounds: str | None = 'minlat="34.0" minlon="-118.0" maxlat="35.0" maxlon="-117.0"'
) -> Path:
    """A made-up extract in OSM XML; ``bounds`` None leaves the header box out."""
    nodes = "".join(
        f'<node id="{i}" lat="{lat}" lon="{lon}" {META}/>' for i, (lon, lat) in NODES.items()
    )

    def way(i: int, refs: list[int], tags: dict[str, str]) -> str:
        nds = "".join(f'<nd ref="{r}"/>' for r in refs)
        tag = "".join(f'<tag k="{k}" v="{v}"/>' for k, v in tags.items())
        return f'<way id="{i}" {META}>{nds}{tag}</way>'

    ways = "".join(
        [
            way(10, [1, 2], {"highway": "residential", "name": "Inside Street"}),
            way(11, [3, 4], {"highway": "primary", "name": "Crossing Road"}),  # no node inside
            way(12, [5, 6], {"highway": "residential", "name": "Far Lane"}),
            way(13, [1, 99], {"highway": "service"}),  # node 99 is not in the extract
            way(14, [1, 2], {"building": "yes"}),  # not a street
            way(15, [7, 8], {"highway": "residential", "name": "Corner Cut"}),
            way(16, [1], {"highway": "residential"}),  # a single node, no line
        ]
    )
    header = "" if bounds is None else f"<bounds {bounds}/>"
    path.write_text(
        f'<?xml version="1.0"?><osm version="0.6" generator="test">{header}{nodes}{ways}</osm>'
    )
    return path


def test_the_ways_touching_the_box_are_taken_with_their_nodes(tmp_path: Path) -> None:
    answer, dropped = read(_extract(tmp_path / "region.osm"), osm.padded(BOUNDS))
    ways = {e["id"]: e for e in answer["elements"] if e["type"] == "way"}
    nodes = {e["id"] for e in answer["elements"] if e["type"] == "node"}
    assert set(ways) == {10, 11}
    assert nodes == {1, 2, 3, 4}  # not 7 and 8: their line misses the box
    assert dropped == 1
    assert ways[11]["tags"] == {"highway": "primary", "name": "Crossing Road"}
    assert ways[10]["timestamp"] == "2026-01-02T03:04:05Z"
    # Overpass lists the ways first, then their nodes.
    kinds = [e["type"] for e in answer["elements"]]
    assert kinds == sorted(kinds, key=lambda k: k != "way")


def test_the_cut_is_built_like_a_download(tmp_path: Path) -> None:
    raw = tmp_path / "osm"
    saved = cut(_extract(tmp_path / "region.osm"), BOUNDS, raw)
    note = json.loads((raw / "overpass_streets.metadata.json").read_text())
    assert note["bounds_west_south_east_north"] == list(osm.padded(BOUNDS))
    assert note["map_as_of"] == "latest"
    assert "region.osm" in note["source"]
    assert "region.osm" in (raw / "overpass_query.txt").read_text()
    table = gpd.read_parquet(streets.build(saved, tmp_path / "network", "EPSG:32611"))
    assert set(table.name) == {"Inside Street", "Crossing Road"}


def test_a_saved_cut_is_reused_and_another_box_refused(tmp_path: Path) -> None:
    extract, raw = _extract(tmp_path / "region.osm"), tmp_path / "osm"
    cut(extract, BOUNDS, raw)
    extract.unlink()  # reused: the extract is not read again
    assert cut(extract, BOUNDS, raw).exists()
    with pytest.raises(ValueError, match="another area"):
        cut(extract, (-117.3, 34.4, -117.2, 34.5), raw)


def test_a_box_beyond_the_extract_writes_nothing(tmp_path: Path) -> None:
    extract = _extract(
        tmp_path / "region.osm", 'minlat="34.0" minlon="-118.0" maxlat="34.5" maxlon="-117.0"'
    )
    with pytest.raises(ValueError, match="outside the extract"):
        cut(extract, BOUNDS, tmp_path / "osm")
    assert not (tmp_path / "osm").exists()


def test_a_box_with_no_streets_writes_nothing(tmp_path: Path) -> None:
    extract = _extract(tmp_path / "region.osm")
    with pytest.raises(ValueError, match="no streets"):
        cut(extract, (-117.95, 34.05, -117.9, 34.1), tmp_path / "osm")
    assert not (tmp_path / "osm" / "overpass_streets.json").exists()


def test_an_extract_without_a_box_is_read_with_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    extract = _extract(tmp_path / "region.osm", bounds=None)
    answer, _ = read(extract, osm.padded(BOUNDS))
    assert {e["id"] for e in answer["elements"] if e["type"] == "way"} == {10, 11}
    assert "no box" in caplog.text
