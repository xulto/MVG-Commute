"""MVG API client and commute planning.

Pure Python + aiohttp, no Home Assistant imports, so it can be used from the
CLI and tested on its own. Uses the unofficial API behind mvg.de.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import aiohttp

API_URL = "https://www.mvg.de/api/bgw-pt/v3"
MIN_TRANSFER = timedelta(minutes=2)
TRANSPORT_TYPES = ("BUS",)
WALK_TYPE = "PEDESTRIAN"


class MvgError(Exception):
    """Raised when the MVG API cannot be reached or returns garbage."""


@dataclass(frozen=True)
class Station:
    global_id: str
    name: str
    place: str


@dataclass(frozen=True)
class Leg:
    line: str
    transport_type: str
    direction: str
    origin: str
    destination: str
    departure: datetime  # live if available, else planned
    arrival: datetime
    realtime: bool
    cancelled: bool

    @property
    def is_walk(self) -> bool:
        return self.transport_type == WALK_TYPE


@dataclass(frozen=True)
class Connection:
    legs: tuple[Leg, ...]
    walk: timedelta  # walk from home to the first stop

    @property
    def transit_legs(self) -> tuple[Leg, ...]:
        return tuple(leg for leg in self.legs if not leg.is_walk)

    @property
    def leave_at(self) -> datetime:
        return self.legs[0].departure - self.walk

    @property
    def arrival(self) -> datetime:
        return self.legs[-1].arrival

    @property
    def transfer_waits(self) -> list[timedelta]:
        """Slack before boarding each transit leg after the first one."""
        waits = []
        seen_transit = False
        for prev, leg in zip(self.legs, self.legs[1:]):
            seen_transit = seen_transit or not prev.is_walk
            if seen_transit and not leg.is_walk:
                waits.append(leg.departure - prev.arrival)
        return waits

    @property
    def realtime(self) -> bool:
        return all(leg.realtime for leg in self.transit_legs)

    @property
    def cancelled(self) -> bool:
        return any(leg.cancelled for leg in self.legs)

    @property
    def summary(self) -> str:
        return " → ".join(leg.line for leg in self.transit_legs)


def _time(stop: dict, delay_key: str) -> datetime:
    planned = datetime.fromisoformat(stop["plannedDeparture"])
    return planned + timedelta(minutes=stop.get(delay_key) or 0)


def parse_connection(raw: dict, walk: timedelta) -> Connection:
    legs = tuple(
        Leg(
            line=part["line"]["label"],
            transport_type=part["line"]["transportType"],
            direction=part["line"].get("destination", ""),
            origin=part["from"]["name"],
            destination=part["to"]["name"],
            departure=_time(part["from"], "departureDelayInMinutes"),
            arrival=_time(part["to"], "arrivalDelayInMinutes"),
            realtime=bool(part.get("realTime")),
            cancelled=bool(part.get("isCancelled")),
        )
        for part in raw["parts"]
    )
    return Connection(legs=legs, walk=walk)


@dataclass(frozen=True)
class Departure:
    line: str
    transport_type: str
    direction: str
    trip: str  # line + tripCode, the same bus at every stop it serves
    time: datetime  # live if available, else planned
    realtime: bool
    cancelled: bool


def parse_departure(raw: dict) -> Departure:
    return Departure(
        line=raw["label"],
        transport_type=raw["transportType"],
        direction=raw.get("destination", ""),
        trip=f'{raw["label"]}:{raw["tripCode"]}',
        time=datetime.fromtimestamp(raw["realtimeDepartureTime"] / 1000, UTC),
        realtime=bool(raw.get("realtime")),
        cancelled=bool(raw.get("cancelled")),
    )


def _rides(boarding: list[Departure], alighting: list[Departure], origin: str, destination: str) -> list[Leg]:
    """Buses that call at the boarding stop and later at the alighting stop."""
    later = {d.trip: d for d in alighting}
    rides = []
    for dep in boarding:
        arr = later.get(dep.trip)
        if arr is None or arr.time <= dep.time:
            continue  # doesn't serve the next stop, or runs the other way
        rides.append(
            Leg(
                line=dep.line,
                transport_type=dep.transport_type,
                direction=dep.direction,
                origin=origin,
                destination=destination,
                departure=dep.time,
                arrival=arr.time,
                realtime=dep.realtime and arr.realtime,
                cancelled=dep.cancelled or arr.cancelled,
            )
        )
    return sorted(rides, key=lambda leg: leg.departure)


def chain_connections(
    names: list[str], departures: list[list[Departure]], walk: timedelta
) -> list[Connection]:
    """Build connections along a fixed sequence of stops (start, changes..., end).

    For every bus on the first leg, takes the earliest bus on each following leg
    that leaves at least MIN_TRANSFER after arriving.
    """
    legs_rides = [
        _rides(departures[i], departures[i + 1], names[i], names[i + 1])
        for i in range(len(names) - 1)
    ]
    connections = []
    for first in legs_rides[0]:
        legs = [first]
        for rides in legs_rides[1:]:
            ready = legs[-1].arrival + MIN_TRANSFER
            nxt = next((r for r in rides if r.departure >= ready and not r.cancelled), None)
            if nxt is None:
                break
            legs.append(nxt)
        else:
            connections.append(Connection(legs=tuple(legs), walk=walk))
    return connections


def plan(connections: list[Connection], now: datetime) -> list[Connection]:
    """Return the catchable, sensible connections ordered by leave time.

    Drops cancelled ones, ones you can no longer reach on foot, ones with a
    transfer tighter than MIN_TRANSFER, and ones dominated by another that
    lets you leave no earlier and arrive earlier.
    """
    usable = [
        c
        for c in connections
        if c.transit_legs
        and not c.cancelled
        and c.leave_at >= now
        and all(w >= MIN_TRANSFER for w in c.transfer_waits)
    ]
    usable.sort(key=lambda c: (-c.leave_at.timestamp(), c.arrival))
    kept: list[Connection] = []
    for c in usable:
        if not kept or c.arrival < kept[-1].arrival:
            kept.append(c)
    kept.reverse()
    return kept


class MvgClient:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _get(self, path: str, params: dict) -> list:
        try:
            async with self._session.get(
                f"{API_URL}/{path}",
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise MvgError(f"MVG request to {path} failed: {err}") from err
        if not isinstance(data, list):
            raise MvgError(f"Unexpected MVG response from {path}")
        return data

    async def search_stations(self, query: str) -> list[Station]:
        data = await self._get("locations", {"query": query})
        return [
            Station(global_id=x["globalId"], name=x["name"], place=x.get("place", ""))
            for x in data
            if x.get("type") == "STATION"
        ]

    async def connections(
        self, origin: str, destination: str, depart_after: datetime, walk: timedelta
    ) -> list[Connection]:
        data = await self._get(
            "routes",
            {
                "originStationGlobalId": origin,
                "destinationStationGlobalId": destination,
                "routingDateTime": depart_after.astimezone(UTC).strftime(
                    "%Y-%m-%dT%H:%M:%S.000Z"
                ),
                "routingDateTimeIsArrival": "false",
                "transportTypes": ",".join(TRANSPORT_TYPES),
            },
        )
        return [parse_connection(raw, walk) for raw in data]

    async def departures(self, station: str) -> list[Departure]:
        data = await self._get(
            "departures",
            {
                "globalId": station,
                "limit": "100",
                "transportTypes": ",".join(TRANSPORT_TYPES),
            },
        )
        return [parse_departure(raw) for raw in data]

    async def chained_connections(self, stations: list[Station], walk: timedelta) -> list[Connection]:
        departures = await asyncio.gather(*(self.departures(s.global_id) for s in stations))
        return chain_connections([s.name for s in stations], list(departures), walk)
