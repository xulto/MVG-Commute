import json
from datetime import datetime, timedelta
from pathlib import Path

from mvg import parse_connection, plan

FIXTURE = Path(__file__).parent / "fixtures" / "routes_oez_west_am_hart.json"
WALK = timedelta(minutes=5)


def at(hhmm: str) -> datetime:
    return datetime.fromisoformat(f"2026-10-08T{hhmm}:00+02:00")


def fixture_connections():
    return [parse_connection(raw, WALK) for raw in json.loads(FIXTURE.read_text())]


def part(line, dep, arr, *, kind="BUS", dep_delay=0, arr_delay=0, cancelled=False):
    return {
        "line": {"label": line, "transportType": kind, "destination": ""},
        "from": {"name": "A", "plannedDeparture": f"2026-10-08T{dep}:00+02:00",
                 "departureDelayInMinutes": dep_delay},
        "to": {"name": "B", "plannedDeparture": f"2026-10-08T{arr}:00+02:00",
               "arrivalDelayInMinutes": arr_delay},
        "realTime": kind != "PEDESTRIAN",
        "isCancelled": cancelled,
    }


def conn(*parts):
    return parse_connection({"parts": list(parts)}, WALK)


def test_parse_applies_live_delays_and_walk():
    first = fixture_connections()[0]  # X35 19:38+1 -> Anhalter Platz 19:44+2 | 180 19:50
    assert first.legs[0].departure == at("19:39")
    assert first.leave_at == at("19:34")
    assert first.transfer_waits == [timedelta(minutes=4)]
    assert first.arrival == at("19:57")
    assert first.summary == "X35 → 180"
    assert first.realtime


def test_plan_on_fixture_drops_dominated_and_keeps_order():
    options = plan(fixture_connections(), now=at("19:30"))
    assert [(c.summary, c.leave_at, c.arrival) for c in options] == [
        ("X35 → 180", at("19:34"), at("19:57")),
        ("X36 → 179 → 172", at("19:46"), at("20:13")),  # beats X36 → 179 (20:14)
        ("X35 → 180", at("19:53"), at("20:17")),
        ("X35 → 180", at("20:14"), at("20:37")),
        ("X35 → 180", at("20:34"), at("20:54")),
    ]


def test_plan_drops_connections_you_can_no_longer_reach():
    options = plan(fixture_connections(), now=at("19:35"))
    assert options[0].leave_at == at("19:46")


def test_transfer_below_buffer_is_dropped_but_exactly_two_minutes_is_ok():
    tight = conn(part("X35", "19:40", "19:49", arr_delay=2), part("179", "19:52", "19:55"))
    ok = conn(part("X36", "19:41", "19:50"), part("178", "19:52", "19:56"))
    assert tight.transfer_waits == [timedelta(minutes=1)]
    assert plan([tight, ok], now=at("19:30")) == [ok]


def test_walk_between_stops_counts_against_buffer():
    c = conn(part("X35", "19:40", "19:50"), part("Fussweg", "19:50", "19:53", kind="PEDESTRIAN"),
             part("180", "19:54", "20:00"))
    assert c.transfer_waits == [timedelta(minutes=1)]
    assert plan([c], now=at("19:30")) == []


def test_leading_walk_leg_is_not_a_transfer():
    c = conn(part("Fussweg", "19:40", "19:47", kind="PEDESTRIAN"), part("178", "19:47", "19:50"))
    assert c.transfer_waits == []
    assert c.leave_at == at("19:35")


def test_cancelled_connection_is_dropped():
    c = conn(part("X35", "19:40", "19:50", cancelled=True), part("179", "19:55", "19:58"))
    assert plan([c], now=at("19:30")) == []


# --- fixed route via a change stop, built from departures ---------------------

from mvg import chain_connections, parse_departure  # noqa: E402

VIA_NAMES = ["Olympia-Einkaufszentrum West", "Anhalter Platz", "Am Hart"]


def fixture_departures():
    return [
        [parse_departure(d) for d in json.loads((FIXTURE.parent / f"departures_{n}.json").read_text())]
        for n in ("oez_west", "anhalter_platz", "am_hart")
    ]


def dep(line, trip, hhmm, *, realtime=True, cancelled=False):
    ms = int(at(hhmm).timestamp() * 1000)
    return parse_departure({"label": line, "transportType": "BUS", "destination": "", "tripCode": trip,
                            "realtimeDepartureTime": ms, "realtime": realtime, "cancelled": cancelled})


def test_chain_on_fixture_follows_the_same_bus_to_am_hart():
    options = plan(chain_connections(VIA_NAMES, fixture_departures(), WALK), now=at("19:30"))
    best = options[0]
    assert best.summary == "X35 → 180"
    assert [(l.origin, l.departure, l.destination, l.arrival) for l in best.legs] == [
        ("Olympia-Einkaufszentrum West", at("19:38"), "Anhalter Platz", at("19:44")),
        ("Anhalter Platz", at("19:50"), "Am Hart", at("19:59")),
    ]
    assert best.leave_at == at("19:33")
    assert best.transfer_waits == [timedelta(minutes=6)]
    # only X35/X36 then 180, never the wrong-direction buses
    assert all(c.summary in ("X35 → 180", "X36 → 180") for c in options)
    assert all(l.destination == "Am Hart" for c in options for l in c.legs[1:])


def test_chain_ignores_buses_going_the_other_way():
    names = ["A", "T", "B"]
    deps = [
        [dep("X35", 1, "19:40"), dep("X35", 2, "19:50")],  # trip 2 reaches T before A
        [dep("X35", 1, "19:46"), dep("X35", 2, "19:44"), dep("180", 7, "19:50"), dep("180", 8, "19:30")],
        [dep("180", 7, "19:58"), dep("180", 8, "19:20")],
    ]
    conns = chain_connections(names, deps, WALK)
    assert [(c.summary, c.arrival) for c in conns] == [("X35 → 180", at("19:58"))]


def test_chain_respects_buffer_and_skips_cancelled_second_bus():
    names = ["A", "T", "B"]
    deps = [
        [dep("X35", 1, "19:40")],
        [dep("X35", 1, "19:46"), dep("180", 7, "19:47"), dep("180", 8, "19:48", cancelled=True),
         dep("180", 9, "19:55")],
        [dep("180", 7, "19:55"), dep("180", 8, "19:56"), dep("180", 9, "20:03")],
    ]
    (c,) = chain_connections(names, deps, WALK)
    assert c.legs[1].departure == at("19:55")
    assert c.transfer_waits == [timedelta(minutes=9)]


def test_chain_drops_first_bus_without_onward_connection():
    names = ["A", "T", "B"]
    deps = [[dep("X35", 1, "19:40")], [dep("X35", 1, "19:46")], []]
    assert chain_connections(names, deps, WALK) == []


def test_chain_live_flag_needs_both_stops_live():
    names = ["A", "T", "B"]
    deps = [
        [dep("X35", 1, "19:40")],
        [dep("X35", 1, "19:46"), dep("180", 7, "19:50")],
        [dep("180", 7, "19:58", realtime=False)],
    ]
    (c,) = chain_connections(names, deps, WALK)
    assert not c.realtime
