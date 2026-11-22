# Demo map files: Claremont, California

These files let the walkthrough and the tests run with no downloads. They hold
map data only. The demo's crashes are made up by `bike_safety_ca.demo` when you
run it and are never stored here.

Claremont was picked only as a small city away from the Los Altos case study.
Nothing in the demo says anything about real crashes there.

| File | What it is | Source and licence |
|---|---|---|
| `city_limit.geojson` | City outline | U.S. Census Bureau cartographic boundary file, 2023 (1:500,000). Public domain. |
| `area.geojson` | The same outline widened by 1.5 km | Derived from the file above. Public domain. |
| `streets.json.gz` | Streets in and around the area, as of 16 November 2026 (UTC), without footpaths: each way's `highway`, `name`, `lanes` and `oneway` tags and its node positions | © OpenStreetMap contributors, [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/). This extract is offered under the same licence. |

The repository's MIT licence covers the code, not `streets.json.gz`. If you
pass the street extract on, keep the OpenStreetMap credit and the ODbL.
