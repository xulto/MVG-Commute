from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

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
    DOMAIN,
    UPDATE_INTERVAL,
)
from .mvg import Connection, MvgClient, MvgError, Station, plan
from .schedule import is_active

_LOGGER = logging.getLogger(__name__)


class MvgCommuteCoordinator(DataUpdateCoordinator[list[Connection]]):
    """Fetches connections and keeps the planned options, best first.

    Only calls the API inside the configured window, or when forced via the
    refresh button. Outside it, existing options just expire as their leave
    time passes.
    """

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
        options = entry.options
        self._walk = timedelta(minutes=options[CONF_WALK_MINUTES])
        self._active_from = dt_util.parse_time(options.get(CONF_ACTIVE_FROM, DEFAULT_ACTIVE_FROM))
        self._active_until = dt_util.parse_time(options.get(CONF_ACTIVE_UNTIL, DEFAULT_ACTIVE_UNTIL))
        self._active_days = options.get(CONF_ACTIVE_DAYS, DEFAULT_ACTIVE_DAYS)
        self._force = False

    def async_track_window_start(self) -> CALLBACK_TYPE:
        """Fetch right when the window opens instead of at the next tick."""

        async def _window_opened(_now) -> None:
            await self.async_refresh()

        start = self._active_from
        return async_track_time_change(
            self.hass, _window_opened, hour=start.hour, minute=start.minute, second=start.second
        )

    async def async_fetch_now(self) -> None:
        """Fetch immediately, even outside the polling window."""
        self._force = True
        await self.async_refresh()

    async def _async_update_data(self) -> list[Connection]:
        now = dt_util.utcnow()
        active = is_active(dt_util.now(), self._active_from, self._active_until, self._active_days)
        if not active and not self._force:
            return plan(self.data or [], now)
        self._force = False
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
