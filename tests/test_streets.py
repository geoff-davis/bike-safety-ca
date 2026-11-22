from __future__ import annotations

import json

from shapely.geometry import box

from bike_safety_ca.download import osm
from bike_safety_ca.network import junctions, streets


def _node(i: int, lon: float, lat: float) -> dict[str, object]:
    return {"type": "node", "id": i, "lon": lon, "lat": lat}


RAW = {
    "elements": [
        {
            "type": "way",
            "id": 10,
            "nodes": [1, 2, 3],
            "tags": {"highway": "secondary", "name": "Main Street", "lanes": "2"},
        },
        {
            "type": "way",
            "id": 11,
            "nodes": [4, 2, 5],
            "tags": {"highway": "residential", "name": "Oak Avenue", "oneway": "yes"},
        },
        {"type": "way", "id": 11, "nodes": [4, 2, 5], "tags": {"highway": "residential"}},
        {"type": "way", "id": 12, "nodes": [1, 99], "tags": {"highway": "residential"}},
        {"type": "way", "id": 13, "nodes": [1, 4], "tags": {"barrier": "fence"}},
        _node(1, -122.002, 37.0),
        _node(2, -122.0, 37.0),
        _node(3, -121.998, 37.0),
        _node(4, -122.0, 37.002),
        _node(5, -122.0, 36.998),
    ]
}


def test_streets_keep_named_columns_and_node_ids() -> None:
    table = streets.streets(RAW)
    assert table.osm_id.tolist() == [10, 11]
    assert table.name.tolist() == ["Main Street", "Oak Avenue"]
    assert table.lanes.tolist()[0] == "2"
    assert table.oneway.tolist()[1] == "yes"
    assert [json.loads(ids) for ids in table.node_ids] == [[1, 2, 3], [4, 2, 5]]
    assert [len(line.coords) for line in table.geometry] == [3, 3]


def test_street_table_gives_an_intersection() -> None:
    table = streets.streets(RAW).to_crs(26910)
    found, names = junctions.build_junctions(table, box(*table.total_bounds).buffer(100))
    assert found.name.tolist() == ["Main Street / Oak Avenue"]
    assert len(names.iloc[0]) == 2


def test_query_covers_the_padded_box() -> None:
    bounds = osm.padded((-122.1, 37.3, -122.0, 37.4), 0.01)
    assert bounds == (-122.11, 37.29, -121.99, 37.41)
    assert 'way["highway"](37.29,-122.11,37.41,-121.99);' in osm.build_query(bounds)


def test_query_can_ask_for_a_past_map() -> None:
    query = osm.build_query((-122.1, 37.3, -122.0, 37.4), date="2026-08-22T23:47:01Z")
    assert query.startswith(
        '[out:json][timeout:600][maxsize:1073741824][date:"2026-08-22T23:47:01Z"];'
    )
