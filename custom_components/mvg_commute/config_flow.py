from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_DESTINATION,
    CONF_DESTINATION_NAME,
    CONF_ORIGIN,
    CONF_ORIGIN_NAME,
    CONF_VIA,
    CONF_VIA_NAME,
    CONF_WALK_MINUTES,
    DEFAULT_WALK_MINUTES,
    DOMAIN,
)
from .mvg import MvgClient, MvgError, Station

MAX_MATCHES = 10

WALK_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=0, max=60, step=1, unit_of_measurement="min", mode=NumberSelectorMode.BOX)
)


def _station_selector(stations: list[Station]) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(value=s.global_id, label=f"{s.name} ({s.place})") for s in stations
            ],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


class MvgCommuteConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._origins: list[Station] = []
        self._destinations: list[Station] = []
        self._vias: list[Station] = []
        self._walk_minutes = DEFAULT_WALK_MINUTES

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for station search terms and walk time."""
        errors: dict[str, str] = {}
        if user_input is not None:
            client = MvgClient(async_get_clientsession(self.hass))
            try:
                self._origins = (await client.search_stations(user_input[CONF_ORIGIN]))[:MAX_MATCHES]
                self._destinations = (
                    await client.search_stations(user_input[CONF_DESTINATION])
                )[:MAX_MATCHES]
                via_query = user_input.get(CONF_VIA, "").strip()
                self._vias = (await client.search_stations(via_query))[:MAX_MATCHES] if via_query else []
            except MvgError:
                errors["base"] = "cannot_connect"
            else:
                if not self._origins:
                    errors[CONF_ORIGIN] = "no_station"
                if not self._destinations:
                    errors[CONF_DESTINATION] = "no_station"
                if via_query and not self._vias:
                    errors[CONF_VIA] = "no_station"
            if not errors:
                self._walk_minutes = int(user_input[CONF_WALK_MINUTES])
                return await self.async_step_stations()

        schema = vol.Schema(
            {
                vol.Required(CONF_ORIGIN): str,
                vol.Required(CONF_DESTINATION): str,
                vol.Optional(CONF_VIA): str,
                vol.Required(CONF_WALK_MINUTES, default=DEFAULT_WALK_MINUTES): WALK_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_stations(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick the exact stations from the search matches."""
        errors: dict[str, str] = {}
        if user_input is not None:
            origin = next(s for s in self._origins if s.global_id == user_input[CONF_ORIGIN])
            dest = next(s for s in self._destinations if s.global_id == user_input[CONF_DESTINATION])
            via = next((s for s in self._vias if s.global_id == user_input.get(CONF_VIA)), None)
            ids = [s.global_id for s in (origin, via, dest) if s]
            if len(set(ids)) != len(ids):
                errors["base"] = "same_station"
            else:
                await self.async_set_unique_id("_".join(ids))
                self._abort_if_unique_id_configured()
                data = {
                    CONF_ORIGIN: origin.global_id,
                    CONF_ORIGIN_NAME: origin.name,
                    CONF_DESTINATION: dest.global_id,
                    CONF_DESTINATION_NAME: dest.name,
                }
                if via:
                    data |= {CONF_VIA: via.global_id, CONF_VIA_NAME: via.name}
                return self.async_create_entry(
                    title=f"{origin.name} → {dest.name}",
                    data=data,
                    options={CONF_WALK_MINUTES: self._walk_minutes},
                )

        schema = {
            vol.Required(CONF_ORIGIN, default=self._origins[0].global_id): _station_selector(
                self._origins
            ),
        }
        if self._vias:
            schema[vol.Required(CONF_VIA, default=self._vias[0].global_id)] = _station_selector(
                self._vias
            )
        schema[vol.Required(CONF_DESTINATION, default=self._destinations[0].global_id)] = (
            _station_selector(self._destinations)
        )
        return self.async_show_form(step_id="stations", data_schema=vol.Schema(schema), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> MvgCommuteOptionsFlow:
        return MvgCommuteOptionsFlow()


class MvgCommuteOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={CONF_WALK_MINUTES: int(user_input[CONF_WALK_MINUTES])})
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_WALK_MINUTES, default=self.config_entry.options[CONF_WALK_MINUTES]
                    ): WALK_SELECTOR
                }
            ),
        )
