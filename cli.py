"""Try the planner without Home Assistant.

    uv run --no-project --with aiohttp cli.py "Olympia-Einkaufszentrum West" "Am Hart" --walk 5
    uv run --no-project --with aiohttp cli.py "Olympia-Einkaufszentrum West" "Am Hart" --via "Anhalter Platz"
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "custom_components" / "mvg_commute"))

import aiohttp  # noqa: E402
from mvg import MvgClient, plan  # noqa: E402


async def main(origin: str, destination: str, via: str | None, walk_minutes: int) -> None:
    walk = timedelta(minutes=walk_minutes)
    async with aiohttp.ClientSession() as session:
        client = MvgClient(session)
        stations = []
        for query in (origin, via, destination) if via else (origin, destination):
            found = await client.search_stations(query)
            if not found:
                sys.exit(f"No station found for {query!r}")
            stations.append(found[0])
        now = datetime.now().astimezone()
        if via:
            conns = await client.chained_connections(stations, walk)
        else:
            conns = await client.connections(stations[0].global_id, stations[-1].global_id, now + walk, walk)
    print(f"{' → '.join(s.name for s in stations)}  (walk {walk_minutes} min)\n")
    for c in plan(conns, now):
        waits = ", ".join(f"{int(w.total_seconds() // 60)}" for w in c.transfer_waits) or "-"
        live = "live" if c.realtime else "planned"
        print(f"leave {c.leave_at.astimezone():%H:%M}  arrive {c.arrival.astimezone():%H:%M}  {c.summary:<18} wait {waits} min  [{live}]")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("origin")
    p.add_argument("destination")
    p.add_argument("--via", help="change stop; follow actual buses instead of the journey planner")
    p.add_argument("--walk", type=int, default=5)
    a = p.parse_args()
    asyncio.run(main(a.origin, a.destination, a.via, a.walk))
