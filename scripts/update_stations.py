"""Regenerate the bundled MVG station list used by the setup dropdowns.

    python3 scripts/update_stations.py

Keeps only MVG's own stations (the ids from /.rest/zdm/mvgStationGlobalIds),
with names and places from /api/bgw-pt/v3/stations.
"""

import json
import urllib.request
from pathlib import Path

OUT = Path(__file__).parent.parent / "custom_components" / "mvg_commute" / "stations.json"


def fetch(url: str):
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.load(resp)


def main() -> None:
    ids = set(fetch("https://www.mvg.de/.rest/zdm/mvgStationGlobalIds"))
    stations = fetch("https://www.mvg.de/api/bgw-pt/v3/stations")["stations"]
    rows = sorted(
        {(s["globalId"], s["name"], s.get("place", "")) for s in stations if s["globalId"] in ids},
        key=lambda r: (r[1].casefold(), r[2], r[0]),
    )
    missing = ids - {r[0] for r in rows}
    OUT.write_text(
        "[\n" + ",\n".join(json.dumps(list(r), ensure_ascii=False) for r in rows) + "\n]\n",
        encoding="utf-8",
    )
    print(f"wrote {len(rows)} stations to {OUT}" + (f" ({len(missing)} ids without details)" if missing else ""))


if __name__ == "__main__":
    main()
