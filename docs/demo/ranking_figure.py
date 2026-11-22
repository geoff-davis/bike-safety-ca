"""Draw the demo city's ranking for the README (made-up crashes only).

Usage: python docs/demo/ranking_figure.py <repo> <out.png>
"""

import sys
from pathlib import Path

import geopandas as gpd
import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from bike_safety_ca import CAR, CYCLISTS, demo
from bike_safety_ca import config as settings
from bike_safety_ca.io import read_shapes
from bike_safety_ca.model.crash_history import rank_intersections
from bike_safety_ca.network import area as outlines
from bike_safety_ca.network import junctions
from bike_safety_ca.network import streets as street_table
from bike_safety_ca.report import crashes as crash_table

ROOT = Path(sys.argv[1])
OUT = Path(sys.argv[2])

config = settings.load(ROOT / "config/demo_claremont.yaml")
assert config.synthetic
data_root = ROOT / "data/demo/processed"
if not demo.paths(data_root.parent, config.crs)["truth"].exists():
    demo.build(config, data_root.parent)
chosen = outlines.chosen(config, data_root / "boundaries")
outline = read_shapes(chosen["area"]).to_crs(config.crs).union_all()
limit = read_shapes(chosen["city_limit"]).to_crs(config.crs).union_all()
ways = gpd.read_parquet(street_table.path(data_root / "network", config.crs))
sites, roads = junctions.build_junctions(ways, outline)
crashes = crash_table.load(data_root / "crashes", config, outline)
hits = junctions.assign_crashes(
    crashes[crashes.group.isin([*CYCLISTS, CAR])], sites.geometry, roads
)
bike = junctions.count_at(hits[hits.group.isin(CYCLISTS)], sites.index)
car = junctions.count_at(hits[hits.group.eq(CAR)], sites.index)
ranked = rank_intersections(bike, car, roads.to_dict())
# The title and the README caption say "ranked by the model"; refuse the fallback ordering.
if ranked["method"] != "street-length model":
    sys.exit(f"ranked by the {ranked['method']}, not the model: {ranked['reason']}")

inside = sites.geometry.within(limit)
score = ranked["score"][inside]
order = score.rank(ascending=False, method="first")
bands = pd.cut(order, [0, 50, 150, 300, 500, len(order)], labels=False)
colours = ["#b91c1c", "#ea580c", "#f59e0b", "#fcd34d", "#e5e7eb"]
sizes = [60, 34, 20, 12, 6]
labels = ["Top 50", "51 to 150", "151 to 300", "301 to 500", "The rest"]
crashed = bike.reindex(order.index) > 0

fig, ax = plt.subplots(figsize=(9, 9))
streets = ways[ways.highway.isin(junctions.HIGHWAY_RANK) & ways.intersects(limit)]
streets.clip(limit.buffer(150)).plot(ax=ax, color="#d5d9df", linewidth=0.6)
gpd.GeoSeries([limit]).boundary.plot(ax=ax, color="#6b7280", linewidth=1)
for b in reversed(range(5)):
    idx = order.index[bands.to_numpy() == b]
    sites.loc[idx].plot(ax=ax, color=colours[b], markersize=sizes[b], zorder=2 + (4 - b))
sites.loc[order.index[crashed.to_numpy()]].plot(
    ax=ax, facecolor="none", edgecolor="#1f2328", markersize=8, linewidth=0.6, zorder=8
)
ax.set_axis_off()
ax.set_title("Every intersection in the demo city, ranked by the model", loc="left", fontsize=13)
handles = [
    Line2D([], [], marker="o", ls="", color=c, markersize=m**0.5 + 2, label=text)
    for c, m, text in zip(colours, sizes, labels)
]
handles.append(
    Line2D(
        [],
        [],
        marker="o",
        ls="",
        markerfacecolor="none",
        markeredgecolor="#1f2328",
        markersize=4,
        label="Has a past bike crash",
    )
)
ax.legend(handles=handles, loc="lower left", frameon=True, fontsize=10, title="Rank")
fig.text(
    0.01,
    0.01,
    "Real Claremont streets (© OpenStreetMap contributors, ODbL); made-up crashes.",
    fontsize=8,
    color="#6b7280",
)
fig.tight_layout()
fig.savefig(OUT, dpi=110)
print("wrote", OUT)
