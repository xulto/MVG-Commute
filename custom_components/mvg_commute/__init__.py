"""MVG Commute: when to leave for a Munich public transport connection."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import MvgCommuteCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]

type MvgCommuteConfigEntry = ConfigEntry[MvgCommuteCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: MvgCommuteConfigEntry) -> bool:
    coordinator = MvgCommuteCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MvgCommuteConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: MvgCommuteConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
