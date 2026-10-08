from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MvgCommuteConfigEntry
from .entity import MvgCommuteEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MvgCommuteConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([MvgLiveDataSensor(entry.runtime_data, entry, "live_data")])


class MvgLiveDataSensor(MvgCommuteEntity, BinarySensorEntity):
    """On when every bus of the best connection has live times."""

    @property
    def is_on(self) -> bool | None:
        options = self.coordinator.data
        return options[0].realtime if options else None
