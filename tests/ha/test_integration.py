"""End-to-end through a real HA core with the MVG API mocked."""

import json
from datetime import datetime
from pathlib import Path

from freezegun.api import FrozenDateTimeFactory
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.mvg_commute.const import DOMAIN
from custom_components.mvg_commute.mvg import API_URL

FIXTURES = Path(__file__).parent.parent / "fixtures"
OEZ = {"name": "Olympia-Einkaufszentrum West", "globalId": "de:09162:318", "place": "München", "type": "STATION"}
AM_HART = {"name": "Am Hart", "globalId": "de:09162:760", "place": "München", "type": "STATION"}
ANHALTER = {"name": "Anhalter Platz", "globalId": "de:09162:329", "place": "München", "type": "STATION"}
PREFIX = "olympia_einkaufszentrum_west_am_hart"
EVENING = {"active_from": "18:00:00", "active_until": "21:00:00", "active_days": ["thu"]}


def berlin(iso: str) -> datetime:
    return datetime.fromisoformat(f"2026-10-08T{iso}+02:00")  # a Thursday


def mock_api(aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(
        f"{API_URL}/routes",
        json=json.loads((FIXTURES / "routes_oez_west_am_hart.json").read_text()),
    )
    for gid, name in (("318", "oez_west"), ("329", "anhalter_platz"), ("760", "am_hart")):
        aioclient_mock.get(
            f"{API_URL}/departures",
            params={"globalId": f"de:09162:{gid}", "limit": "100", "transportTypes": "BUS"},
            json=json.loads((FIXTURES / f"departures_{name}.json").read_text()),
        )


def api_calls(aioclient_mock: AiohttpClientMocker) -> int:
    return aioclient_mock.call_count


async def add_entry(hass: HomeAssistant, *, via: bool = False, **settings) -> ConfigEntry:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    user_input = {"origin": OEZ["globalId"], "destination": AM_HART["globalId"], "walk_minutes": 5, **settings}
    if via:
        user_input["via"] = ANHALTER["globalId"]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Olympia-Einkaufszentrum West → Am Hart"
    await hass.async_block_till_done()
    return result["result"]


def state(hass: HomeAssistant, entity: str) -> str:
    return hass.states.get(entity).state


async def test_router_mode_entities(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(berlin("19:30:00"))
    mock_api(aioclient_mock)
    await add_entry(hass, **EVENING)

    assert state(hass, f"sensor.{PREFIX}_leave_at") == "2026-10-08T17:34:00+00:00"
    assert state(hass, f"sensor.{PREFIX}_minutes_until_leave") == "4"
    assert state(hass, f"sensor.{PREFIX}_arrival") == "2026-10-08T17:57:00+00:00"
    assert state(hass, f"sensor.{PREFIX}_transfer_wait") == "4"
    route = hass.states.get(f"sensor.{PREFIX}_route")
    assert route.state == "X35 → 180"
    assert route.attributes["legs"][0]["line"] == "X35"
    assert state(hass, f"sensor.{PREFIX}_next_option_leave_at") == "2026-10-08T17:46:00+00:00"
    assert state(hass, f"binary_sensor.{PREFIX}_live_data") == "on"
    assert hass.states.get(f"button.{PREFIX}_refresh") is not None


async def test_change_at_stop_follows_actual_buses(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(berlin("19:30:00"))
    mock_api(aioclient_mock)
    entry = await add_entry(hass, via=True, **EVENING)

    assert entry.data["via_name"] == "Anhalter Platz"
    assert state(hass, f"sensor.{PREFIX}_leave_at") == "2026-10-08T17:33:00+00:00"
    assert state(hass, f"sensor.{PREFIX}_arrival") == "2026-10-08T17:59:00+00:00"
    route = hass.states.get(f"sensor.{PREFIX}_route")
    assert route.state == "X35 → 180"
    assert route.attributes["legs"][1]["to"] == "Am Hart"
    assert not any("/routes" in str(call[1]) for call in aioclient_mock.mock_calls)


async def test_polls_every_five_minutes_inside_window(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(berlin("19:30:00"))
    mock_api(aioclient_mock)
    await add_entry(hass, **EVENING)
    assert api_calls(aioclient_mock) == 1

    freezer.tick(240)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert api_calls(aioclient_mock) == 1

    freezer.tick(61)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert api_calls(aioclient_mock) == 2


async def test_no_api_calls_outside_window_until_it_opens(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(berlin("17:52:30"))
    mock_api(aioclient_mock)
    await add_entry(hass, **EVENING)
    assert api_calls(aioclient_mock) == 0
    assert state(hass, f"sensor.{PREFIX}_leave_at") == "unknown"

    freezer.move_to(berlin("17:57:31"))  # a regular 5-minute tick, still outside
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert api_calls(aioclient_mock) == 0

    freezer.move_to(berlin("18:00:00"))  # window opens: fetch right away
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert api_calls(aioclient_mock) == 1
    assert state(hass, f"sensor.{PREFIX}_leave_at") != "unknown"


async def test_refresh_button_fetches_outside_window_and_data_expires(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(berlin("19:30:00"))
    mock_api(aioclient_mock)
    await add_entry(hass)  # default window 06:00–10:00, so 19:30 is outside
    assert api_calls(aioclient_mock) == 0

    await hass.services.async_call("button", "press", {"entity_id": f"button.{PREFIX}_refresh"}, blocking=True)
    await hass.async_block_till_done()
    assert api_calls(aioclient_mock) == 1
    assert state(hass, f"sensor.{PREFIX}_leave_at") == "2026-10-08T17:34:00+00:00"

    # Next tick outside the window: no fetch, but the 19:34 option has gone.
    freezer.move_to(berlin("19:35:01"))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert api_calls(aioclient_mock) == 1
    assert state(hass, f"sensor.{PREFIX}_leave_at") == "2026-10-08T17:46:00+00:00"


async def test_options_flow_updates_walk_and_window(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_api(aioclient_mock)
    entry = await add_entry(hass)
    assert entry.options == {
        "walk_minutes": 5,
        "active_from": "06:00:00",
        "active_until": "10:00:00",
        "active_days": ["mon", "tue", "wed", "thu", "fri"],
    }

    result = await hass.config_entries.options.async_init(entry.entry_id)
    new = {"walk_minutes": 8, "active_from": "16:30:00", "active_until": "19:00:00", "active_days": []}
    result = await hass.config_entries.options.async_configure(result["flow_id"], new)
    assert result["errors"] == {"active_days": "no_days"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], new | {"active_days": ["mon", "fri"]}
    )
    await hass.async_block_till_done()
    assert entry.options == new | {"active_days": ["mon", "fri"]}


async def test_station_pickers_validate_input(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    picker = next(k for k in result["data_schema"].schema if k == "origin")
    options = result["data_schema"].schema[picker].config["options"]
    assert len(options) > 1000
    assert {"value": "de:09162:329", "label": "Anhalter Platz"} in options
    assert result["data_schema"].schema[picker].config["custom_value"] is True

    base = {"walk_minutes": 5, **EVENING}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], base | {"origin": "Nowhere", "destination": AM_HART["globalId"]}
    )
    assert result["errors"] == {"origin": "unknown_station"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], base | {"origin": AM_HART["globalId"], "destination": AM_HART["globalId"]}
    )
    assert result["errors"] == {"base": "same_station"}

    # Typed exact name (any case) is accepted as well as a picked id.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], base | {"origin": "olympia-einkaufszentrum west", "destination": AM_HART["globalId"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "origin": "de:09162:318",
        "origin_name": "Olympia-Einkaufszentrum West",
        "destination": "de:09162:760",
        "destination_name": "Am Hart",
    }


async def test_reconfigure_changes_stations(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(berlin("19:30:00"))
    mock_api(aioclient_mock)
    entry = await add_entry(hass, via=True, **EVENING)
    other = await add_entry(hass, **EVENING)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    assert result["step_id"] == "reconfigure"
    # Would turn this entry into a copy of the other one.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"origin": OEZ["globalId"], "destination": AM_HART["globalId"]}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"origin": "de:09162:756", "via": ANHALTER["globalId"], "destination": OEZ["globalId"]},
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.title == "Am Hart Süd → Olympia-Einkaufszentrum West"
    assert entry.unique_id == "de:09162:756_de:09162:329_de:09162:318"
    assert entry.data["destination_name"] == "Olympia-Einkaufszentrum West"
    assert other.title == "Olympia-Einkaufszentrum West → Am Hart"
