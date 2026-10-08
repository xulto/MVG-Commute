from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DESTINATION,
    CONF_DESTINATION_NAME,
    CONF_ORIGIN,
    CONF_ORIGIN_NAME,
    CONF_VIA,
    CONF_VIA_NAME,
    CONF_WALK_MINUTES,
    DOMAIN,
    UPDATE_INTERVAL,
)
from .mvg import Connection, MvgClient, MvgError, Station, plan

_LOGGER = logging.getLogger(__name__)


class MvgCommuteCoordinator(DataUpdateCoordinator[list[Connection]]):
    """Fetches connections and keeps the planned options, best first."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=UPDATE_INTERVAL,
        )
        self._client = MvgClient(async_get_clientsession(hass))
        data = entry.data
        self._origin = Station(data[CONF_ORIGIN], data[CONF_ORIGIN_NAME], "")
        self._destination = Station(data[CONF_DESTINATION], data[CONF_DESTINATION_NAME], "")
        self._via = Station(data[CONF_VIA], data[CONF_VIA_NAME], "") if data.get(CONF_VIA) else None
        self._walk = timedelta(minutes=entry.options[CONF_WALK_MINUTES])

    async def _async_update_data(self) -> list[Connection]:
        now = dt_util.utcnow()
        try:
            if self._via:
                # Fixed route: follow the actual buses through the change stop.
                connections = await self._client.chained_connections(
                    [self._origin, self._via, self._destination], self._walk
                )
            else:
                connections = await self._client.connections(
                    self._origin.global_id, self._destination.global_id, now + self._walk, self._walk
                )
        except MvgError as err:
            raise UpdateFailed(str(err)) from err
        return plan(connections, now)
