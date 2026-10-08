from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TimeSelector,
)

from .const import (
    CONF_ACTIVE_DAYS,
    CONF_ACTIVE_FROM,
    CONF_ACTIVE_UNTIL,
    CONF_DESTINATION,
    CONF_DESTINATION_NAME,
    CONF_ORIGIN,
    CONF_ORIGIN_NAME,
    CONF_VIA,
    CONF_VIA_NAME,
    CONF_WALK_MINUTES,
    DEFAULT_ACTIVE_DAYS,
    DEFAULT_ACTIVE_FROM,
    DEFAULT_ACTIVE_UNTIL,
    DEFAULT_WALK_MINUTES,
    DOMAIN,
)
from .mvg import Station
from .schedule import WEEKDAYS

STATIONS_FILE = Path(__file__).parent / "stations.json"

WALK_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=0, max=60, step=1, unit_of_measurement="min", mode=NumberSelectorMode.BOX)
)
DAYS_SELECTOR = SelectSelector(
    SelectSelectorConfig(options=list(WEEKDAYS), multiple=True, translation_key="weekdays")
)
DEFAULT_SETTINGS = {
    CONF_WALK_MINUTES: DEFAULT_WALK_MINUTES,
    CONF_ACTIVE_FROM: DEFAULT_ACTIVE_FROM,
    CONF_ACTIVE_UNTIL: DEFAULT_ACTIVE_UNTIL,
    CONF_ACTIVE_DAYS: DEFAULT_ACTIVE_DAYS,
}


def _settings_schema(current: dict[str, Any]) -> dict:
    """Walk time and polling window, shared by setup and the options flow."""
    current = DEFAULT_SETTINGS | current
    return {
        vol.Required(CONF_WALK_MINUTES, default=current[CONF_WALK_MINUTES]): WALK_SELECTOR,
        vol.Required(CONF_ACTIVE_FROM, default=current[CONF_ACTIVE_FROM]): TimeSelector(),
        vol.Required(CONF_ACTIVE_UNTIL, default=current[CONF_ACTIVE_UNTIL]): TimeSelector(),
        vol.Required(CONF_ACTIVE_DAYS, default=current[CONF_ACTIVE_DAYS]): DAYS_SELECTOR,
    }


def _settings(user_input: dict[str, Any]) -> dict[str, Any]:
    return {
        CONF_WALK_MINUTES: int(user_input[CONF_WALK_MINUTES]),
        CONF_ACTIVE_FROM: user_input[CONF_ACTIVE_FROM],
        CONF_ACTIVE_UNTIL: user_input[CONF_ACTIVE_UNTIL],
        CONF_ACTIVE_DAYS: user_input[CONF_ACTIVE_DAYS],
    }


def _label(station: Station) -> str:
    return station.name if station.place == "München" else f"{station.name}, {station.place}"


def _load_stations() -> list[Station]:
    rows = json.loads(STATIONS_FILE.read_text(encoding="utf-8"))
    return [Station(global_id=gid, name=name, place=place) for gid, name, place in rows]


async def _async_stations(hass: HomeAssistant) -> dict[str, Station]:
    """The bundled MVG stations by id, loaded once per HA run."""
    cache = hass.data.setdefault(DOMAIN, {})
    if "stations" not in cache:
        cache["stations"] = {s.global_id: s for s in await hass.async_add_executor_job(_load_stations)}
    return cache["stations"]


def _stations_schema(stations: dict[str, Station]) -> dict:
    """Searchable pickers. custom_value is what makes HA render a search box."""
    picker = SelectSelector(
        SelectSelectorConfig(
            options=[SelectOptionDict(value=s.global_id, label=_label(s)) for s in stations.values()],
            mode=SelectSelectorMode.DROPDOWN,
            custom_value=True,
        )
    )
    return {
        vol.Required(CONF_ORIGIN): picker,
        vol.Optional(CONF_VIA): picker,
        vol.Required(CONF_DESTINATION): picker,
    }


def _pick_stations(
    stations: dict[str, Station], user_input: dict[str, Any], errors: dict[str, str]
) -> dict[str, Any]:
    """Validate picked stations and return them as entry data.

    Free text (allowed by the picker) only counts if it is a station's exact name.
    """
    by_label = {_label(s).casefold(): s for s in stations.values()}
    picked: dict[str, Station] = {}
    for key in (CONF_ORIGIN, CONF_VIA, CONF_DESTINATION):
        value = (user_input.get(key) or "").strip()
        if not value:
            continue
        station = stations.get(value) or by_label.get(value.casefold())
        if station is None:
            errors[key] = "unknown_station"
        else:
            picked[key] = station
    ids = [s.global_id for s in picked.values()]
    if not errors and len(set(ids)) != len(ids):
        errors["base"] = "same_station"
    if errors:
        return {}
    data = {}
    names = {CONF_ORIGIN: CONF_ORIGIN_NAME, CONF_VIA: CONF_VIA_NAME, CONF_DESTINATION: CONF_DESTINATION_NAME}
    for key, name_key in names.items():
        if key in picked:
            data |= {key: picked[key].global_id, name_key: picked[key].name}
    return data


def _unique_id(data: dict[str, Any]) -> str:
    return "_".join(data[k] for k in (CONF_ORIGIN, CONF_VIA, CONF_DESTINATION) if k in data)


def _title(data: dict[str, Any]) -> str:
    return f"{data[CONF_ORIGIN_NAME]} → {data[CONF_DESTINATION_NAME]}"


class MvgCommuteConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick stations, walk time and polling window."""
        stations = await _async_stations(self.hass)
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _pick_stations(stations, user_input, errors)
            if not user_input[CONF_ACTIVE_DAYS]:
                errors[CONF_ACTIVE_DAYS] = "no_days"
            if not errors:
                await self.async_set_unique_id(_unique_id(data))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=_title(data), data=data, options=_settings(user_input))

        schema = vol.Schema({**_stations_schema(stations), **_settings_schema({})})
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the stations of an existing entry."""
        entry = self._get_reconfigure_entry()
        stations = await _async_stations(self.hass)
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _pick_stations(stations, user_input, errors)
            if not errors:
                unique_id = _unique_id(data)
                if unique_id != entry.unique_id:
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()
                return self.async_update_reload_and_abort(
                    entry, unique_id=unique_id, title=_title(data), data=data
                )

        schema = vol.Schema(_stations_schema(stations))
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or dict(entry.data)),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> MvgCommuteOptionsFlow:
        return MvgCommuteOptionsFlow()


class MvgCommuteOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_ACTIVE_DAYS]:
                return self.async_create_entry(data=_settings(user_input))
            errors[CONF_ACTIVE_DAYS] = "no_days"
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(_settings_schema(dict(self.config_entry.options))),
            errors=errors,
        )
