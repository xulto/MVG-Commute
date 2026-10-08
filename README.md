# MVG Commute

Home Assistant integration that tells you **when to leave** for a Munich bus
connection with transfers, using live MVG data. It only suggests connections
where every transfer leaves at least **2 minutes** (counting live delays), and it
skips connections that a faster one dominates.

It uses the unofficial API behind mvg.de (`/api/bgw-pt/v3`), so MVG can break it
without notice.

## Install (Home Assistant OS)

**HACS:** push this repo to GitHub, then go to HACS → ⋮ → *Custom repositories*,
add `https://github.com/xulto/MVG-Commute` with type *Integration*, install **MVG Commute**, and restart HA.

**Manual:** copy `custom_components/mvg_commute/` into `/config/custom_components/`
(using the Samba, SSH or Studio Code Server add-on) and restart HA.

Then go to *Settings → Devices & services → Add integration → MVG Commute*,
and pick the start station, an optional **Change at** station and the
destination. Type in a field to search. The list contains MVG's ~1,180
stations (Munich and a few neighbours like Germering and Unterföhring) and is
bundled with the integration, so it opens instantly and needs no network.
On the same page, set your walking time to the start stop and the polling
window.

Add the integration once per direction. Use *Configure* to change the walking
time and polling window, and *Reconfigure* to change the stations.

## Two modes

- **Without a change stop**, MVG's journey planner picks the connections. It may
  route you via other lines or stops, and may have you get off a stop early and
  walk.
- **With a change stop**, the integration follows the actual buses. It reads
  live departures at all three stops and matches each bus across stops by its
  trip number. A bus counts for a leg only if it calls at both stops in that
  order, so you don't configure lines and wrong-direction buses drop out.
  Arrival is that bus's live time at your destination stop. For each first bus,
  it picks the earliest second bus that leaves at least 2 minutes after arrival.

  The destination must not be the last stop of the line, because the API only
  lists departures, not arrivals. Opposite directions can use different stops.
  For example, the 180 towards Kieferngarten stops at *Am Hart*, but towards
  Berduxstraße it only stops at *Am Hart Süd*. So the return trip has to start
  at Am Hart Süd.

## Entities (one device per direction)

| Entity | Meaning |
|---|---|
| `sensor.*_leave_at` | When to leave home for the best connection. Attribute `options` lists every sensible connection. |
| `sensor.*_minutes_until_leave` | Minutes left until you need to leave; recalculated every minute |
| `sensor.*_arrival` | Arrival time of the best connection |
| `sensor.*_transfer_wait` | Shortest transfer wait of the best connection (min) |
| `sensor.*_route` | Lines, e.g. `X35 → 180`. Attribute `legs` gives per-leg times. |
| `sensor.*_next_option_leave_at` | When to leave for the next connection after that |
| `binary_sensor.*_live_data` | On when every bus of the best connection has live times |
| `button.*_refresh` | Fetch new data now |

## Polling

Each direction only polls during its own window: every **5 minutes**,
starting right when the window opens. You set the window when adding the
integration and can change it later under *Configure*:

- **Poll from / Poll until**: default 06:00–10:00. Setting both to the same
  time polls all day. An end time earlier than the start runs past midnight,
  e.g. 22:00–01:00.
- **Poll on**: default Monday to Friday. A window that runs past midnight
  counts for the day it started.

For example, use 06:30–09:00 for the outbound direction and 16:00–19:00 for
the way home.

Outside the window there are no API calls. The sensors keep the last data and
drop each connection once its leave time has passed. The **Refresh** button
always fetches, inside or outside the window.

In change-stop mode each fetch is 3 requests (one per stop), otherwise 1.

## Development

`custom_components/mvg_commute/mvg.py` contains the API client and planning
logic and doesn't import Home Assistant. Try it from the CLI:

```sh
uv run --no-project --with aiohttp cli.py "Olympia-Einkaufszentrum West" "Am Hart" --walk 5
uv run --no-project --with aiohttp cli.py "Olympia-Einkaufszentrum West" "Am Hart" --via "Anhalter Platz"
uv run --no-project --with aiohttp cli.py "Am Hart Süd" "Olympia-Einkaufszentrum West" --via "Anhalter Platz"
```

Refresh the bundled station list (`custom_components/mvg_commute/stations.json`):

```sh
python3 scripts/update_stations.py
```

Run the tests (unit tests plus integration tests in a real HA core):

```sh
uv run --no-project --python 3.13 --with pytest-homeassistant-custom-component pytest tests
```
