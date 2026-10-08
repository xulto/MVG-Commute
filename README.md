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

Then go to *Settings → Devices & services → Add integration → MVG Commute*:
1. Enter search terms for the start and destination stations, an optional
   **Change at** station, and your walking time to the start stop.
2. Pick the exact stations from the matches.

Add the integration once per direction. To change the walking time later, use the
integration's *Configure* option.

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

The integration polls every 2 minutes. To poll only on demand, turn off
*System options → Enable polling for updates* on the integration entry and press
the refresh button from an automation, for example on weekday mornings:

```yaml
automation:
  - alias: Refresh commute before work
    triggers:
      - trigger: time_pattern
        minutes: "/2"
    conditions:
      - condition: time
        after: "07:00:00"
        before: "09:00:00"
        weekday: [mon, tue, wed, thu, fri]
    actions:
      - action: button.press
        target:
          entity_id: button.olympia_einkaufszentrum_west_am_hart_refresh
```

## Development

`custom_components/mvg_commute/mvg.py` contains the API client and planning
logic and doesn't import Home Assistant. Try it from the CLI:

```sh
uv run --no-project --with aiohttp cli.py "Olympia-Einkaufszentrum West" "Am Hart" --walk 5
uv run --no-project --with aiohttp cli.py "Olympia-Einkaufszentrum West" "Am Hart" --via "Anhalter Platz"
uv run --no-project --with aiohttp cli.py "Am Hart Süd" "Olympia-Einkaufszentrum West" --via "Anhalter Platz"
```

Run the tests (unit tests plus integration tests in a real HA core):

```sh
uv run --no-project --python 3.13 --with pytest-homeassistant-custom-component pytest tests
```
