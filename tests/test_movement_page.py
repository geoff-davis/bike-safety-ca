"""The crash movement map's panel, filters and key, run on made-up crashes.

The page's script is JavaScript, so these tests fill the template with
``movement.page`` and run its script in node against a small stand-in for the
browser and the map library: a window 1000 by 600 pixels showing latitude
34.00 to 34.10 and longitude -118.10 to -118.00.  They skip where node is
missing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from bike_safety_ca import ADULT
from bike_safety_ca import config as settings
from bike_safety_ca.report import movement
from bike_safety_ca.report.crashes import describe

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

CONFIG = settings.load(Path("config/los_altos.yaml"))
HOOK = "cyclist going straight; car or truck right turn, same direction"
ALONE = "cyclist going straight" + movement.NO_OTHER

# A stand-in for the browser and Leaflet: enough for the page's script to run and be read back.
BROWSER = r"""
const T_={groups:[],ids:{}};
T_.el=id=>({id,value:"",checked:false,textContent:"",_h:"",_kids:{},_rows:{},listeners:{},style:{},dataset:{},
  classList:{add(){},remove(){}},
  get innerHTML(){return this._h;},set innerHTML(v){this._h=String(v);this._kids={};this._rows={};},
  addEventListener(t,f){(this.listeners[t]=this.listeners[t]||[]).push(f);},
  fire(t){(this.listeners[t]||[]).slice().forEach(f=>f({}));},
  querySelector(sel){return this._kids[sel]=this._kids[sel]||T_.el(sel);},
  querySelectorAll(sel){ // table rows of one class, with their data-k
    if(!this._rows[sel]){const out=[],re=new RegExp('<tr class="'+sel.slice(1)+'[^"]*" data-k="([^"]*)"',"g");let m;
      while((m=re.exec(this._h))){const e=T_.el(sel);e.dataset.k=m[1].replace(/&quot;/g,'"').replace(/&lt;/g,"<").replace(/&gt;/g,">").replace(/&amp;/g,"&");out.push(e);}
      this._rows[sel]=out;}
    return this._rows[sel];}});
for(const id of ["who","area","y0","y1","com","mv","ws","dk","view","rkw","print","count","panel","pkey","pfilters","map"])T_.ids[id]=T_.el(id);
T_.ids.who.value="all";T_.ids.area.value="all";
globalThis.document={documentElement:{},body:T_.el("body"),
  querySelectorAll(){return [];},addEventListener(){}, // the tooltip script; hover is not run here
  getElementById(id){if(T_.ids[id])return T_.ids[id]; // anything else is inside the panel
    const p=T_.ids.panel;return p._h.includes('id="'+id+'"')?p.querySelector("#"+id):null;}};
globalThis.getComputedStyle=()=>({getPropertyValue:n=>n}); // a colour is its variable's name
globalThis.location={hash:""};globalThis.history={replaceState(){}};globalThis.innerHeight=900;globalThis.addEventListener=()=>{};
T_.mark=(kind,at,o)=>({kind,at,o:o||{},bindPopup(f){this.popup=f;return this;},addTo(g){if(g&&g._items)g._items.push(this);return this;},setStyle(){}});
T_.map={_z:14,_b:{s:34.0,w:-118.1,n:34.1,e:-118.0},_size:{x:1000,y:600},_on:{},
  setView(c,z){if(z!==undefined)this._z=z;return this;},
  on(t,f){for(const k of t.split(" "))(this._on[k]=this._on[k]||[]).push(f);return this;},
  fire(t){(this._on[t]||[]).slice().forEach(f=>f({}));},
  getZoom(){return this._z;},getCenter(){const b=this._b;return {lat:(b.s+b.n)/2,lng:(b.w+b.e)/2};},getSize(){return this._size;},
  getBounds(){const mk=(s,w,n,e)=>({contains:([la,lo])=>la>=s&&la<=n&&lo>=w&&lo<=e,pad:f=>mk(s-(n-s)*f,w-(e-w)*f,n+(n-s)*f,e+(e-w)*f)});
    const b=this._b;return mk(b.s,b.w,b.n,b.e);},
  latLngToContainerPoint(ll){const [la,lo]=Array.isArray(ll)?ll:[ll.lat,ll.lng],b=this._b,z=this._size;
    const pt=(x,y)=>({x,y,add:([dx,dy])=>pt(x+(dx||0),y+(dy||0))});
    return pt((lo-b.w)/(b.e-b.w)*z.x,(b.n-la)/(b.n-b.s)*z.y);},
  attributionControl:{addAttribution(){}},createPane(){return {style:{}};},hasLayer(){return true;},invalidateSize(){}};
T_.control=()=>({addTo(m){if(this.onAdd)this._c=this.onAdd(m);return this;},getContainer(){return this._c;}});
globalThis.window={print(){},L:{map:()=>T_.map,svg:()=>({}),polyline:()=>T_.mark("line"),tileLayer:()=>({}),divIcon:o=>o,
  layerGroup(){const g={_items:[],addTo(){return this;},clearLayers(){this._items=[];}};T_.groups.push(g);return g;},
  circleMarker:(at,o)=>T_.mark("circle",at,o),marker:(at,o)=>T_.mark("marker",at,o),
  control:Object.assign(()=>T_.control(),{layers:()=>T_.control(),scale:()=>T_.control()}),
  DomUtil:{create:()=>T_.el("legend")},DomEvent:{disableClickPropagation(){},disableScrollPropagation(){}}}};
// For the scenarios: move the window, change a filter, and read the page back.
T_.view=(z,b)=>{T_.map._z=z;if(b)T_.map._b=b;T_.map.fire("zoomend");T_.map.fire("moveend");};
T_.set=(id,v)=>{if(typeof v==="boolean")T_.ids[id].checked=v;else T_.ids[id].value=v;T_.ids[id].fire("change");};
T_.text=h=>h.replace(/<[^>]*>/g," ").replace(/&amp;/g,"&").replace(/\s+/g," ").trim();
T_.panel=()=>T_.text(T_.ids.panel.innerHTML);
T_.count=()=>T_.ids.count.textContent;
T_.crashes=()=>T_.groups.flatMap(g=>g._items).filter(x=>x.popup&&x.o.radius!==undefined||x.kind==="marker"&&x.popup); // one mark per crash drawn
T_.key=()=>T_.text(lg.getContainer().querySelector(".kb").innerHTML);
T_.line=()=>T_.text(lg.getContainer().querySelector(".k1").innerHTML);
T_.pick=k=>T_.ids.panel.querySelectorAll(".pat").find(e=>e.dataset.k===k).fire("click");
"""


def _bike(move: str = "B", bearing: float = 0, fault: bool = False) -> dict[str, Any]:
    return {"k": "bicycle", "b": bearing, "d": "N", "m": move, "f": fault, "a": "", "s": True}


def _car(move: str = "D", bearing: float = 0, fault: bool = False) -> dict[str, Any]:
    return {"k": "car or truck", "b": bearing, "d": "N", "m": move, "f": fault, "a": "", "s": True}


def _crash(lat: float = 34.05, lon: float = -118.05, **kw: Any) -> dict[str, Any]:
    """One made-up crash as ``movement.crash_rows`` writes it: a right hook away from a corner."""
    row: dict[str, Any] = {
        "ws": "",
        "wc": False,
        "wu": False,
        "lat": lat,
        "lon": lon,
        "y": 2022,
        "ym": "Mar 2022",
        "h": 8,
        "st": "Main Street",
        "cause": "Improper turning",
        "coll": "sideswipe",
        "child": False,
        "adult": True,
        "com": False,
        "la": True,
        "ap": False,
        "p": [_bike(), _car()],
        "sv": "4",
        "lt": "A",
        "pk": HOOK,
        "pd": "northbound",
        "cs": ["Main Street"],
        "si": None,
        "w": [],
        "fit": "fits",
    }
    return {**row, **kw}


def _run(rows: list[dict[str, Any]], scenario: str, config: settings.Config = CONFIG) -> Any:
    """Run the page on ``rows``, then ``scenario``, which prints one JSON value."""
    page = movement.page(rows, {key: [] for key in "MTLSP"}, [], config, (34.05, -118.05), [])
    script = page[page.rindex("<script>") + len("<script>") : page.rindex("</script>")]
    out = subprocess.run(
        [NODE or "node", "-e", "\n".join([BROWSER, script, scenario])],
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout)


LEVELS = {"city": 14, "neighbourhood": 15, "intersection": 18}


@pytest.mark.parametrize("zoom", LEVELS.values(), ids=LEVELS.keys())
def test_in_view_is_the_visible_window_at_every_zoom(zoom: int) -> None:
    # Three crashes in the window and three 12 pixels above its top edge, on another street.
    # Each is at its own place, since crashes at one point are fanned out around it when zoomed in.
    along = (-118.07, -118.05, -118.03)
    inside = [_crash(lon=lon) for lon in along]
    outside = [_crash(34.102, lon, st="Far Road", cs=["Far Road"]) for lon in along]
    found = _run(
        inside + outside,
        f"T_.view({zoom});console.log(JSON.stringify([T_.count(),T_.panel(),T_.crashes().length]));",
    )
    count, panel, drawn = found
    assert count.startswith("6 cyclist crashes match the filters")
    assert "3 of the 6 crashes that match the filters are in view." in panel
    assert "Main Street" in panel and "Far Road" not in panel
    assert drawn == 6  # the margin still draws the three just outside; it only is not counted


def test_a_single_crash_reads_as_one() -> None:
    found = _run([_crash()], "console.log(JSON.stringify([T_.count(),T_.panel()]));")
    assert found[0].startswith("1 cyclist crash matches the filters")
    assert "1 of the 1 crash that matches the filters is in view. 0 at 0 intersections." in found[1]


# The wrong-side tests below take their rows from the real row generation (``describe`` and
# ``crash_rows``) on made-up records, so no flag on a row is set by hand.
CRS = 26910
STREETS = gpd.GeoDataFrame(
    {"highway": ["secondary", "residential"], "name": ["Main Street", "Oak Avenue"]},
    geometry=[
        LineString([(579_000, 4_137_000), (581_000, 4_137_000)]),  # east-west
        LineString([(580_000, 4_136_000), (580_000, 4_138_000)]),  # north-south
    ],
    crs=CRS,
)
WRONG_SIDE, UNSAFE_SPEED = "05", "03"  # cause codes (codes.CAUSES)
# Parties are (party type, at fault, direction, movement, vehicle type).
CYCLIST_NORTH = ("4", "N", "N", "B", "L")
DRIVER_TURNING = ("1", "Y", "S", "D", "A")  # southbound, turning right, at fault


def _records(crashes: list[tuple[str, list[tuple[Any, ...]]]]) -> list[dict[str, Any]]:
    """Map rows for made-up crashes on Oak Avenue, each ``(cause code, parties)``."""
    ids = [f"m{i}" for i in range(len(crashes))]
    table = gpd.GeoDataFrame(
        {
            "merged_id": ids,
            "year": 2022,
            "group": ADULT,
            "PRIMARY_RD": "OAK AV",
            "SECONDARY_RD": None,
        },
        geometry=[Point(580_000, 4_137_200 + 60 * i) for i in range(len(crashes))],
        crs=CRS,
    )
    detail = pd.DataFrame(
        {
            "merged_id": ids,
            "CASE_ID": ids,
            "ccrs_collision_id": None,
            "collision_date": "2022-07-12",
            "collision_hour": pd.array([15] * len(ids), dtype="Int64"),
            "CITY": "Los Altos",
            "PCF_VIOL_CATEGORY": [cause for cause, _ in crashes],
            "TYPE_OF_COLLISION": "D",
        }
    )
    parties = pd.DataFrame(
        [
            (case, number, kind, fault, "30", direction, move, vehicle)
            for case, (_, people) in zip(ids, crashes, strict=True)
            for number, (kind, fault, direction, move, vehicle) in enumerate(people, 1)
        ],
        columns=[
            "CASE_ID",
            "PARTY_NUMBER",
            "PARTY_TYPE",
            "AT_FAULT",
            "PARTY_AGE",
            "DIR_OF_TRAVEL",
            "MOVE_PRE_ACC",
            "STWD_VEHICLE_TYPE",
        ],
    ).assign(ccrs_collision_id=None, source="tims")
    described = describe(table, detail, CONFIG)
    return movement.crash_rows(described, parties, STREETS, CONFIG.child_max_age)


# After the page has drawn the collision diagrams around the rows: for each crash, the side
# each cyclist is drawn on (1 with traffic, -1 against it), the page's category, and the
# number of crashes each wrong-side filter returns.
DRAWN = (
    "const la=DATA.map(r=>r.lat),lo=DATA.map(r=>r.lon);"
    "T_.view(18,{s:Math.min(...la)-.001,n:Math.max(...la)+.001,w:Math.min(...lo)-.002,e:Math.max(...lo)+.002});"
    "const first=r=>r.p.find(p=>p.k==='bicycle'&&p.b!==null),"
    "sides=r=>r.p.filter(p=>p.k==='bicycle').map(p=>Math.sign(offset(p,r))*(p===first(r)&&r.plan&&r.plan.inferred?-1:1));"
    "const out={sides:DATA.map(sides),side:DATA.map(side),panel:T_.panel(),popup:DATA.map(r=>T_.text(popup(r))),n:{}};"
    "for(const v of ['coded','inf','either','unclear']){T_.set('ws',v);out.n[v]=parseInt(T_.count());}"
    "console.log(JSON.stringify(out));"
)


@pytest.mark.parametrize("fault", ["N", "", "y", float("nan")], ids=["N", "blank", "y", "NaN"])
def test_wrong_side_cited_with_the_cyclist_not_at_fault_leaves_the_cyclist_with_traffic(
    fault: Any,
) -> None:
    # The driver is at fault for the wrong side.  The movements alone (a car turning right
    # into an oncoming cyclist) would suggest the cyclist rode against traffic.
    cyclist = (CYCLIST_NORTH[0], fault, *CYCLIST_NORTH[2:])
    rows = _records([(WRONG_SIDE, [cyclist, DRIVER_TURNING])])
    (row,) = rows
    assert (row["wc"], row["wu"], row["ws"]) == (False, True, "")
    assert row["fit"] in ("fits", "nomeet") and movement.wrong_side(row) == "unclear"
    found = _run(rows, DRAWN)
    assert found["sides"] == [[1]] and found["side"] == ["unclear"]
    assert found["n"] == {"coded": 0, "inf": 0, "either": 0, "unclear": 1}
    assert "Wrong side cited, party unclear:" in found["popup"][0]
    assert "wrong-side or sidewalk riding" not in found["popup"][0]
    # The same movements with another cause are suggested by the movements, drawn dotted.
    (other,) = _records([(UNSAFE_SPEED, [cyclist, DRIVER_TURNING])])
    assert other["ws"] and movement.wrong_side(other) == "suggested"


def test_only_the_cyclist_at_fault_for_the_wrong_side_is_drawn_against_traffic() -> None:
    at_fault = ("4", "Y", "S", "B", "L")
    rows = _records([(WRONG_SIDE, [CYCLIST_NORTH, at_fault, ("1", "N", "N", "B", "A")])])
    (row,) = rows
    assert (row["wc"], row["wu"]) == (True, False) and movement.wrong_side(row) == "coded"
    assert [bool(p.get("wr")) for p in row["p"]] == [False, True, False]
    found = _run(rows, DRAWN)
    assert found["sides"] == [[1, -1]] and found["side"] == ["coded"]
    assert found["n"] == {"coded": 1, "inf": 0, "either": 1, "unclear": 0}


def test_crossing_into_the_opposing_lane_is_drawn_across_and_is_not_wrong_side_riding() -> None:
    crossed = ("4", "Y", "N", "N", "L")
    rows = _records([(UNSAFE_SPEED, [crossed, ("1", "N", "S", "B", "A")])])
    (row,) = rows
    assert (row["wc"], row["wu"], row["ws"]) == (False, False, "")
    assert row["fit"] == "fits" and movement.wrong_side(row) == ""
    found = _run(rows, DRAWN)
    assert found["sides"] == [[-1]] and found["side"] == [""]
    assert found["n"] == {"coded": 0, "inf": 0, "either": 0, "unclear": 0}
    assert "Crossed into the opposing lane:" in found["popup"][0]
    assert "rong-side riding coded" not in found["popup"][0]
    assert "Wrong side cited" not in found["popup"][0]


def test_a_third_party_the_cyclist_already_meets_leaves_nothing_suggested() -> None:
    # The cyclist and driver alone would suggest wrong-side riding (see above), but the
    # cyclist's own side already crosses the path of a pedestrian walking east.
    walker = ("2", "N", "E", "B", "N")
    quiet_driver = (DRIVER_TURNING[0], "N", *DRIVER_TURNING[2:])
    rows = _records([(UNSAFE_SPEED, [CYCLIST_NORTH, quiet_driver, walker])])
    (row,) = rows
    assert (row["wc"], row["wu"], row["ws"], row["fit"]) == (False, False, "", "fits")
    assert movement.wrong_side(row) == ""
    found = _run(rows, DRAWN)
    assert found["sides"] == [[1]] and found["side"] == [""]
    assert found["n"] == {"coded": 0, "inf": 0, "either": 0, "unclear": 0}
    assert "wrong-side or sidewalk riding" not in found["popup"][0]
    assert "against traffic" not in found["popup"][0]


def test_three_cited_crashes_on_a_street_are_three_unclear_and_no_riding() -> None:
    rows = _records([(WRONG_SIDE, [CYCLIST_NORTH, DRIVER_TURNING])] * 3)
    found = _run(rows, DRAWN)
    assert found["sides"] == [[1]] * 3
    assert "Wrong-side riding Cited, party unclear 3 Oak Avenue 0 0 0 3" in found["panel"]
    assert "3 3 Wrong side cited, party unclear." in found["panel"]  # in view, all matching
    assert found["n"] == {"coded": 0, "inf": 0, "either": 0, "unclear": 3}


def test_the_page_and_python_put_a_crash_in_the_same_wrong_side_category() -> None:
    rows = _records(
        [
            (WRONG_SIDE, [CYCLIST_NORTH, DRIVER_TURNING]),  # cited, party unclear
            (WRONG_SIDE, [("4", "Y", "N", "B", "L"), DRIVER_TURNING]),  # coded: at fault
            (UNSAFE_SPEED, [("4", "N", "N", "Q", "L"), DRIVER_TURNING]),  # coded: own movement
            (UNSAFE_SPEED, [CYCLIST_NORTH, DRIVER_TURNING]),  # suggested by the movements
            (UNSAFE_SPEED, [CYCLIST_NORTH, ("1", "Y", "S", "B", "A")]),  # head on: meets against
            (UNSAFE_SPEED, [CYCLIST_NORTH, ("1", "Y", "N", "D", "A")]),  # a right hook: none
        ]
    )
    expected = ["unclear", "coded", "coded", "suggested", "suggested", ""]
    assert [movement.wrong_side(row) for row in rows] == expected
    found = _run(rows, DRAWN)
    assert found["side"] == expected
    assert found["sides"] == [[1], [-1], [-1], [-1], [-1], [1]]
    assert found["n"] == {"coded": 2, "inf": 2, "either": 4, "unclear": 1}


def test_no_other_party_leaves_out_crashes_with_no_party_records() -> None:
    rows = [_crash(p=[], pk=""), _crash(p=[_bike()], pk=ALONE), _crash()]
    found = _run(rows, "T_.set('mv','solo');console.log(JSON.stringify([T_.count(),T_.panel()]));")
    assert found[0].startswith("1 cyclist crash matches the filters")
    assert "No other party recorded: 1" in found[1]


def test_headings_follow_the_configs_child_age() -> None:
    rows = [_crash(child=True, adult=False) for _ in range(3)]
    config = replace(CONFIG, child_max_age=16)
    panel = _run(rows, "console.log(JSON.stringify(T_.panel()));", config)
    assert "Street 16 or under Fatal or serious" in panel
    page = movement.page(rows, {key: [] for key in "MTLSP"}, [], config, (34.05, -118.05), [])
    assert "18 or under" not in page


def test_a_picked_pattern_is_named_with_a_way_out_after_its_row_has_gone() -> None:
    # Two hooks in the window and four crashes of other kinds; then the window moves off one hook.
    rows = [_crash(), _crash(lat=34.09)] + [_crash(pk=f"other {i}") for i in range(4)]
    found = _run(
        rows,
        f"const faint=()=>T_.crashes().filter(x=>x.o.fillOpacity<.5).length,out={{}};T_.view(15);"
        f"T_.pick({json.dumps(HOOK)});out.picked=faint();"
        "T_.view(15,{s:34.0,w:-118.1,n:34.07,e:-118.0});out.moved=faint();out.panel=T_.panel();"
        "document.getElementById('unpick').fire('click');out.cleared=faint();"
        "T_.view(15,{s:34.0,w:-118.1,n:34.1,e:-118.0});"
        f"T_.pick({json.dumps(HOOK)});out.again=faint();T_.set('who','adult');out.filtered=faint();"
        "console.log(JSON.stringify(out));",
    )
    assert found["picked"] == 4 and found["moved"] == 4
    assert f"Picked pattern: {HOOK}. 1 in view." in found["panel"]
    assert "Show every crash" in found["panel"]
    assert found["cleared"] == 0
    assert found["again"] == 4 and found["filtered"] == 0  # a new filter drops the picked pattern


def test_the_key_lists_only_what_is_drawn_at_each_zoom() -> None:
    rows = [_crash(child=True, adult=False)]
    found = _run(
        rows,
        "const out={};for(const z of [14,15,18]){T_.view(z);out[z]={key:T_.key(),line:T_.line(),"
        "ring:T_.crashes().map(x=>x.o.color)};}console.log(JSON.stringify(out));",
    )
    city, near, corner = found["14"], found["15"], found["18"]
    for level in (city, near):
        assert "cyclist 18 or under" in level["key"] and "ring: after dark" not in level["key"]
        assert level["line"] == ""
        # A child's outline has its own colour: not the bicycle red, which reads as a serious injury.
        assert level["ring"] == ["--child"]
    assert "1 and 10 crashes" in city["key"] and "1 and 10 crashes" not in near["key"]
    assert "ring: after dark" in corner["key"] and "18 or under" not in corner["key"]
    # With the key closed, one line still says what the arrow colours are.
    assert corner["line"] == "Arrows: bicycle car or truck motorcycle pedestrian bus or other"


def test_long_tables_say_how_many_rows_were_left_out() -> None:
    # Fourteen streets with three crashes each, given last street first, and seventeen patterns twice.
    rows = [_crash(cs=[f"S{i:02d} Street"], pk=f"pattern {i:02d}") for i in range(13, -1, -1)] * 3
    rows += [_crash(cs=[], pk=f"pattern {i}") for i in range(14, 17)] * 2
    panel = _run(rows, "console.log(JSON.stringify(T_.panel()));")
    assert "and 2 more streets with 3 or more crashes." in panel
    assert "S11 Street" in panel and "S12 Street" not in panel  # ties go by name, not record order
    assert "and 2 more repeated patterns." in panel


def test_what_a_streets_crashes_have_in_common_has_a_row_of_its_own() -> None:
    page = _run(
        [_crash() for _ in range(3)], "console.log(JSON.stringify(T_.ids.panel.innerHTML));"
    )
    assert f'<tr class="sub"><td></td><td colspan="5">{HOOK} (3; 3 sideswipe)' in page
    assert "<th>In common</th>" not in page
