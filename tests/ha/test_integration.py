"""End-to-end through a real HA core with the MVG API mocked."""

import json
from datetime import datetime
from pathlib import Path

from freezegun.api import FrozenDateTimeFactory
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.mvg_commute.const import DOMAIN
from custom_components.mvg_commute.mvg import API_URL

FIXTURES = Path(__file__).parent.parent / "fixtures"
OEZ = {"name": "Olympia-Einkaufszentrum West", "globalId": "de:09162:318", "place": "München", "type": "STATION"}
AM_HART = {"name": "Am Hart", "globalId": "de:09162:760", "place": "München", "type": "STATION"}


def mock_api(aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{API_URL}/locations", params={"query": "OEZ"}, json=[OEZ])
    aioclient_mock.get(f"{API_URL}/locations", params={"query": "Am Hart"}, json=[AM_HART])
    aioclient_mock.get(
        f"{API_URL}/routes",
        json=json.loads((FIXTURES / "routes_oez_west_am_hart.json").read_text()),
    )


async def test_config_flow_and_entities(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(datetime.fromisoformat("2026-10-08T19:30:00+02:00"))
    mock_api(aioclient_mock)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"origin": "OEZ", "destination": "Am Hart", "walk_minutes": 5}
    )
    assert result["step_id"] == "stations"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"origin": "de:09162:318", "destination": "de:09162:760"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Olympia-Einkaufszentrum West → Am Hart"
    await hass.async_block_till_done()

    prefix = "olympia_einkaufszentrum_west_am_hart"
    assert hass.states.get(f"sensor.{prefix}_leave_at").state == "2026-10-08T17:34:00+00:00"
    assert hass.states.get(f"sensor.{prefix}_minutes_until_leave").state == "4"
    assert hass.states.get(f"sensor.{prefix}_arrival").state == "2026-10-08T17:57:00+00:00"
    assert hass.states.get(f"sensor.{prefix}_transfer_wait").state == "4"
    route = hass.states.get(f"sensor.{prefix}_route")
    assert route.state == "X35 → 180"
    assert route.attributes["legs"][0]["line"] == "X35"
    assert hass.states.get(f"sensor.{prefix}_next_option_leave_at").state == "2026-10-08T17:46:00+00:00"
    assert hass.states.get(f"binary_sensor.{prefix}_live_data").state == "on"
    assert hass.states.get(f"button.{prefix}_refresh") is not None


async def test_options_flow_updates_walk(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    mock_api(aioclient_mock)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"origin": "OEZ", "destination": "Am Hart", "walk_minutes": 5}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"origin": "de:09162:318", "destination": "de:09162:760"}
    )
    entry = result["result"]
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"walk_minutes": 8})
    await hass.async_block_till_done()
    assert entry.options == {"walk_minutes": 8}


ANHALTER = {"name": "Anhalter Platz", "globalId": "de:09162:329", "place": "München", "type": "STATION"}


async def test_change_at_stop_follows_actual_buses(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(datetime.fromisoformat("2026-10-08T19:30:00+02:00"))
    mock_api(aioclient_mock)
    aioclient_mock.get(f"{API_URL}/locations", params={"query": "Anhalter"}, json=[ANHALTER])
    for gid, name in (("318", "oez_west"), ("329", "anhalter_platz"), ("760", "am_hart")):
        aioclient_mock.get(
            f"{API_URL}/departures",
            params={"globalId": f"de:09162:{gid}", "limit": "100", "transportTypes": "BUS"},
            json=json.loads((FIXTURES / f"departures_{name}.json").read_text()),
        )

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"origin": "OEZ", "destination": "Am Hart", "via": "Anhalter", "walk_minutes": 5}
    )
    assert result["step_id"] == "stations"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"origin": "de:09162:318", "via": "de:09162:329", "destination": "de:09162:760"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["via_name"] == "Anhalter Platz"
    await hass.async_block_till_done()

    prefix = "olympia_einkaufszentrum_west_am_hart"
    assert hass.states.get(f"sensor.{prefix}_leave_at").state == "2026-10-08T17:33:00+00:00"
    assert hass.states.get(f"sensor.{prefix}_arrival").state == "2026-10-08T17:59:00+00:00"
    route = hass.states.get(f"sensor.{prefix}_route")
    assert route.state == "X35 → 180"
    assert route.attributes["legs"][1]["to"] == "Am Hart"
    assert not any("/routes" in str(call[1]) for call in aioclient_mock.mock_calls)
