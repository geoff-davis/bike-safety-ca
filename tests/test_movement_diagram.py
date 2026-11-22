"""Where the crash movement map puts a crash in its collision diagram (made-up movements).

The placement code is JavaScript in the map template, so these tests pull the
functions out of it and run them with node.  They skip where node is missing.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from importlib.resources import files

import pytest

from bike_safety_ca.report import diagram

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

FUNCTIONS = (
    "legs",
    "half",
    "lane",
    "against",
    "offset",
    "route",
    "cut",
    "meet",
    "rearer",
    "short",
    "trail",
    "plan",
    "fit",
    "side",
    "counted",
    "street",
)


def _script() -> str:
    page = (files("bike_safety_ca.report") / "movement_map.html").read_text()
    parts = [re.search(r"^const TURN=.*$", page, re.M).group(0)]  # type: ignore[union-attr]
    parts.append(re.search(r"^const KERB=.*$", page, re.M).group(0))  # type: ignore[union-attr]
    parts.append(re.search(r"^const SOLO=.*$", page, re.M).group(0))  # type: ignore[union-attr]
    parts.append(re.search(r"^const ROAD=.*$", page, re.M).group(0))  # type: ignore[union-attr]
    for name in FUNCTIONS:
        start = page.index(f"\nfunction {name}(") + 1
        end = page.index("\nfunction ", start)
        parts.append(page[start:end])
    return "\n".join(["const scale=()=>1,SITE={};", *parts])


def _place(parties: list[dict], **record: object) -> dict:
    """The plan for one crash: ``fit`` is fits, against or nomeet."""
    crash = {"p": parties, "wc": False, "ws": "", **record}
    probe = (
        f"const r={json.dumps(crash)},q=plan(r);"
        "console.log(JSON.stringify(q.nomeet?{fit:'nomeet'}:"
        "{fit:q.inferred?'against':'fits',x:q.x,y:q.y}));"
    )
    out = subprocess.run(
        [NODE or "node", "-e", _script() + "\n" + probe],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout)


def bike(move: str, bearing: float) -> dict:
    return {"k": "bicycle", "m": move, "b": bearing}


def car(move: str, bearing: float) -> dict:
    return {"k": "car or truck", "m": move, "b": bearing}


def test_right_hook_meets_with_both_keeping_right():
    assert _place([bike("B", 0), car("D", 0)])["fit"] == "fits"


def test_right_turn_onto_the_cyclists_street_puts_the_cyclist_against_traffic():
    # Car westbound turning right (north); cyclist southbound.  Keeping right the
    # car turns into the far lanes and the paths never cross.
    placed = _place([bike("B", 180), car("D", 270)])
    assert placed["fit"] == "against"
    assert placed["x"] > 0 > placed["y"]  # the north-east corner, where the car turns


def test_cyclist_already_coded_wrong_side_is_not_inferred():
    assert _place([{**bike("B", 180), "wr": True}, car("D", 270)], wc=True)["fit"] == "fits"


def test_side_by_side_paths_meet():
    assert _place([bike("B", 90), car("B", 90)])["fit"] == "fits"


def test_head_on_puts_the_cyclist_against_traffic():
    assert _place([bike("B", 0), car("B", 180)])["fit"] == "against"


def test_movements_that_never_meet_get_no_crash_point():
    # Cyclist eastbound past a car stopped on the north approach, facing south.
    assert _place([bike("B", 90), car("A", 180)]) == {"fit": "nomeet"}


def test_cyclist_alone_stops_on_the_approach():
    assert _place([bike("B", 90)])["fit"] == "fits"


def test_a_narrow_street_puts_the_crash_near_its_centre():
    # Right hook on a residential corner (half widths 5.8 m) and on the default 10 m.
    narrow = [[0, 5.8], [90, 5.8], [180, 5.8], [270, 5.8]]
    near = _place([bike("B", 0), car("D", 0)], w=narrow)
    far = _place([bike("B", 0), car("D", 0)])
    assert near["fit"] == far["fit"] == "fits"
    assert abs(near["x"]) < 5 < abs(far["x"])  # metres east of the centre line


def test_side_by_side_on_a_wide_road_meets():
    # Cyclist changing lanes beside a car on a six-lane road: different lanes, same half.
    wide = [[0, 11.9], [90, 5.8], [180, 11.9], [270, 5.8]]
    assert _place([bike("J", 0), car("B", 0)], w=wide)["fit"] == "fits"


def test_a_wide_left_turn_beside_the_cyclist_meets():
    # Car turns left onto the cyclist's street and ends up beside them.
    assert _place([bike("B", 270), car("E", 0)])["fit"] == "fits"


def test_a_stopped_car_on_the_cross_street_is_not_side_by_side():
    # Close-ish on a wide road, but at right angles: no crash point made up.
    wide = [[0, 11.9], [90, 11.9], [180, 11.9], [270, 11.9]]
    assert _place([bike("B", 90), car("A", 180)], w=wide) == {"fit": "nomeet"}


def test_a_party_that_never_meets_does_not_hide_one_that_crosses():
    # A car stopped on the north approach, and a northbound car that crosses the cyclist.
    assert _place([bike("B", 90), car("A", 180), car("B", 0)])["fit"] == "fits"


def test_head_on_on_a_narrow_road_is_not_side_by_side():
    narrow = [[0, 3.8], [90, 3.8], [180, 3.8], [270, 3.8]]
    assert _place([bike("B", 0), car("B", 180)], w=narrow)["fit"] == "against"


def test_a_turn_leaves_along_the_real_street_at_a_skewed_corner():
    skewed = [[0, 5.8], [70, 5.8], [180, 5.8], [250, 5.8]]
    probe = (
        f"const W={json.dumps(skewed)},p={json.dumps(car('D', 0))},A=route(p,lane(p.k,p.m,5.8),1,W),"
        "[a,b]=A.slice(-2);console.log(JSON.stringify((Math.atan2(b[0]-a[0],a[1]-b[1])*180/Math.PI+360)%360));"
    )
    out = subprocess.run(
        [NODE or "node", "-e", _script() + "\n" + probe], capture_output=True, text=True, check=True
    )
    assert json.loads(out.stdout) == pytest.approx(70, abs=0.5)


def test_drawn_cyclist_keeps_a_gap_and_the_sorting_is_kept():
    crash = {"p": [bike("B", 0), car("D", 0)], "wc": False, "ws": ""}
    probe = (
        f"const r={json.dumps(crash)},bk=r.p[0],sorted=plan(r,2),drawn=plan(r,2,false);"
        "console.log(JSON.stringify([drawn.paths.get(bk)[0][0]-sorted.paths.get(bk)[0][0],drawn.inferred]));"
    )
    out = subprocess.run(
        [NODE or "node", "-e", _script() + "\n" + probe], capture_output=True, text=True, check=True
    )
    assert json.loads(out.stdout) == [pytest.approx(4), False]


@pytest.mark.parametrize("move", ["B", "E"])
def test_same_way_traffic_is_drawn_just_beside_the_cyclist(move):
    crash = {"p": [bike(move, 0), car(move, 0)], "wc": False, "ws": ""}
    probe = (
        f"const r={json.dumps(crash)},q=plan(r,4,false),[b,c]=r.p.map(p=>q.paths.get(p)[0][0]);"
        "console.log(JSON.stringify(b-c));"
    )
    out = subprocess.run(
        [NODE or "node", "-e", _script() + "\n" + probe], capture_output=True, text=True, check=True
    )
    assert json.loads(out.stdout) == pytest.approx(9)  # BESIDE + GAP pixels, not lanes apart


def test_drawn_spacing_is_kept_through_a_turn():
    # Default 10 m half widths at 4 px a metre: the cyclist at 8.5 m + GAP, the car beside it.
    probe = (
        f"const b={json.dumps(bike('E', 0))},c={json.dumps(car('E', 0))},crash={{p:[b,c],wc:false,ws:''}},"
        "q=plan(crash,4,false),B=q.paths.get(b),C=q.paths.get(c),"
        "rb=route(b,9.5,4,[],1),rc=route(c,7.25,4,[],0,7.25),[x,y]=[rb.slice(-1)[0],rc.slice(-1)[0]];"
        "console.log(JSON.stringify([Math.hypot(x[0]-y[0],x[1]-y[1]),Math.hypot(B[0][0]-C[0][0],B[0][1]-C[0][1])]));"
    )
    out = subprocess.run(
        [NODE or "node", "-e", _script() + "\n" + probe], capture_output=True, text=True, check=True
    )
    exit_gap, approach_gap = json.loads(out.stdout)
    assert exit_gap == pytest.approx(9, abs=0.5) and approach_gap == pytest.approx(9, abs=0.5)


def _drawn(parties: list[dict], k: float = 4, **record: object) -> dict:
    """Drawn paths (screen pixels) for one crash, cyclist keeping right: tip and length of each."""
    crash = {"p": parties, "wc": False, "ws": "", **record}
    probe = (
        f"const r={json.dumps(crash)},q=plan(r,{k},false),len=A=>A.slice(1).reduce((s,b,i)=>"
        "s+Math.hypot(b[0]-A[i][0],b[1]-A[i][1]),0);"
        "console.log(JSON.stringify({x:q.x,y:q.y,p:r.p.map(p=>{const A=q.paths.get(p);"
        "return {tip:A[A.length-1],len:len(A)};})}));"
    )
    out = subprocess.run(
        [NODE or "node", "-e", _script() + "\n" + probe], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


@pytest.mark.parametrize("move", ["L", "K", "J"])
def test_a_car_moving_across_meets_the_cyclist_where_it_crosses(move):
    # Entering traffic from the kerb, pulling in to park, or changing lanes toward the kerb, beside a
    # cyclist going straight the same way.  Before, the car was drawn a lane away (22 px at 4 px a
    # metre) and the crash point was only their nearest approach.
    placed = _place([bike("B", 0), car(move, 0)])
    drawn = _drawn([bike("B", 0), car(move, 0)])
    (bx, by), (cx, cy) = drawn["p"][0]["tip"], drawn["p"][1]["tip"]
    assert placed["fit"] == "fits"
    assert placed["y"] > 10  # metres south of the centre: on the approach, where it moved across
    assert abs(bx - cx) + abs(by - cy) < 2  # both arrows end where the paths cross


def test_in_a_rear_end_the_party_at_fault_stops_short():
    hit = {**car("B", 0), "f": False}
    behind = {**bike("B", 0), "f": True}
    drawn = _drawn([behind, hit], coll="rear end")
    assert drawn["p"][0]["tip"][1] - drawn["p"][1]["tip"][1] == pytest.approx(7, abs=0.5)


def test_in_a_rear_end_a_slowing_car_is_ahead():
    drawn = _drawn([bike("B", 0), car("H", 0)], coll="rear end")
    assert drawn["p"][0]["tip"][1] - drawn["p"][1]["tip"][1] == pytest.approx(7, abs=0.5)


def test_without_a_rear_end_both_arrows_reach_the_crash():
    drawn = _drawn([bike("B", 0), car("H", 0)], coll="sideswipe")
    assert drawn["p"][0]["tip"][1] == pytest.approx(drawn["p"][1]["tip"][1], abs=0.5)


def test_a_car_pulls_out_across_a_cyclist_riding_against_traffic_on_its_side():
    # Southbound cyclist coded wrong side, northbound car entering traffic from the same kerb.
    narrow = [[0, 5.8], [90, 5.8], [180, 5.8], [270, 5.8]]
    drawn = _drawn([{**bike("B", 180), "wr": True}, car("L", 0)], k=1, wc=True, w=narrow)
    (bx, by), (cx, cy) = drawn["p"][0]["tip"], drawn["p"][1]["tip"]
    assert abs(bx - cx) + abs(by - cy) < 0.5  # the car's pull-out reaches the drawn cyclist


# The page's sorting and diagram.fit must agree: the map shows the stored value.
PARITY = [
    ([bike("B", 0), car("D", 0)], {}),
    ([bike("B", 180), car("D", 270)], {}),
    ([{**bike("B", 180), "wr": True}, car("D", 270)], {"wc": True}),
    # Wrong side cited, party unclear: nobody is put against traffic to make the paths meet.
    ([bike("B", 180), car("D", 270)], {"wu": True}),
    ([bike("B", 0), car("B", 180)], {"wu": True}),
    # Two cyclists, the second coded: the first is not moved by the code, nor by inference.
    ([bike("B", 180), {**bike("B", 0), "wr": True}, car("D", 270)], {"wc": True}),
    # A third party the cyclist's own side already meets: nothing is suggested, nobody moved.
    ([bike("B", 0), car("D", 180), {"k": "pedestrian", "m": "B", "b": 90}], {}),
    # Crossed into the opposing lane: drawn across by its own movement.
    ([bike("N", 0), car("B", 180)], {}),
    ([bike("B", 90), car("B", 90)], {}),
    ([bike("B", 0), car("B", 180)], {}),
    ([bike("B", 90), car("A", 180)], {}),
    ([bike("B", 90)], {}),
    ([bike("J", 0), car("B", 0)], {"w": [[0, 11.9], [90, 5.8], [180, 11.9], [270, 5.8]]}),
    ([bike("B", 270), car("E", 0)], {}),
    ([bike("B", 90), car("A", 180)], {"w": [[0, 11.9], [90, 11.9], [180, 11.9], [270, 11.9]]}),
    ([bike("B", 90), car("A", 180), car("B", 0)], {}),
    ([bike("B", 0), car("B", 180)], {"w": [[0, 3.8], [90, 3.8], [180, 3.8], [270, 3.8]]}),
    ([bike("B", 0), car("L", 0)], {}),
    ([bike("B", 0), car("K", 0)], {}),
    ([bike("B", 0), car("J", 0)], {}),
    (
        [{**bike("B", 180), "wr": True}, car("L", 0)],
        {"wc": True, "w": [[0, 5.8], [90, 5.8], [180, 5.8], [270, 5.8]]},
    ),
    ([bike("B", 0), car("F", 90)], {"w": [[14.7, 5.8], [89, 5.8], [178.1, 3.8], [269.5, 5.8]]}),
    ([bike("E", 0), car("D", 180)], {"ws": "cyclist turning left from the right"}),
    ([bike("D", 90), car("M", 0), car("B", 270)], {"w": [[0, 8.5], [90, 5.8], [270, 5.8]]}),
    ([car("B", 0)], {}),
    # Paths that end exactly on one another, or tie, on several compass bearings.
    ([bike("J", 0), car("E", 0)], {}),
    ([bike("J", 270), car("E", 270)], {}),
    ([bike("D", 200), car("L", 200)], {}),
    ([bike("J", 45), car("L", 45)], {}),
    ([bike("J", 45), car("K", 225)], {}),
    ([bike("P", 200), car("F", 200)], {}),
]


@pytest.mark.parametrize(("parties", "record"), PARITY)
def test_the_page_and_python_sort_crashes_alike(parties, record):
    crash = {"wc": False, "wu": False, "ws": "", **record}
    on_page = _place(parties, **crash) if any(p["k"] == "bicycle" for p in parties) else None
    infer = not (crash["wc"] or crash["wu"])
    stored = diagram.fit(parties, crash.get("w", []), bool(crash["ws"]), infer)
    assert stored == (on_page["fit"] if on_page else None)


def test_the_streets_table_counts_wrong_side_riding_and_pairs_patterns_with_collision_type():
    def crash(**kw: object) -> dict:
        return {
            "p": [bike("B", 0), car("D", 0)],
            "wc": False,
            "wu": False,
            "ws": "",
            "pk": "hook",
            "coll": "sideswipe",
            "cause": "Unsafe speed",
            "sv": "4",
            "child": False,
            **kw,
        }

    rows = [
        crash(),
        crash(sv="2", child=True),
        crash(wc=True),  # coded for the cyclist
        crash(wu=True),  # wrong side cited, the cyclist not at fault: not wrong-side riding
        crash(wu=True, fit="against"),  # and not suggested either, whatever is stored
        crash(ws="car turning right met an oncoming cyclist"),  # suggested by the movements
        crash(fit="against"),  # the only way the movements meet
        crash(coll="rear end"),  # still the same pattern
        crash(pk="cyclist going straight; no other party", coll="hit object"),
        crash(pk="other", coll="broadside"),
        crash(pk="other", coll="broadside"),
    ]
    probe = f"console.log(JSON.stringify(street({json.dumps(rows)})));"
    out = subprocess.run(
        [NODE or "node", "-e", _script() + "\n" + probe], capture_output=True, text=True, check=True
    )
    assert json.loads(out.stdout) == {
        "child": 1,
        "serious": 1,
        "wrong": 3,
        "unclear": 2,
        "common": "hook (8; 7 sideswipe); Unsafe speed (11)",
    }


def test_a_lane_change_beside_a_left_turn_sorts_the_same_on_every_bearing():
    # The cyclist's path bends where it is nearest the car's.  Before, the bend counted as part
    # of the straight run on some bearings and of the slanted one on others.
    found = {b: _place([bike("J", b), car("E", b)])["fit"] for b in (0, 90, 200, 270)}
    assert set(found.values()) == {"fits"}
