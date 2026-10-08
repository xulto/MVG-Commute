from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MvgCommuteConfigEntry
from .entity import MvgCommuteEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MvgCommuteConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([MvgRefreshButton(entry.runtime_data, entry, "refresh")])


class MvgRefreshButton(MvgCommuteEntity, ButtonEntity):
    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()
