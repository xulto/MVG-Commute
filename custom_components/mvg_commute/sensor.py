from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from . import MvgCommuteConfigEntry
from .entity import MvgCommuteEntity
from .mvg import Connection


def _minutes(delta: timedelta) -> int:
    return int(delta.total_seconds() // 60)


def _legs(c: Connection) -> list[dict[str, Any]]:
    return [
        {
            "line": leg.line,
            "direction": leg.direction,
            "from": leg.origin,
            "to": leg.destination,
            "departure": leg.departure.isoformat(),
            "arrival": leg.arrival.isoformat(),
            "realtime": leg.realtime,
        }
        for leg in c.legs
    ]


def _options(options: list[Connection]) -> list[dict[str, Any]]:
    return [
        {
            "leave_at": c.leave_at.isoformat(),
            "arrival": c.arrival.isoformat(),
            "route": c.summary,
            "transfer_waits": [_minutes(w) for w in c.transfer_waits],
            "realtime": c.realtime,
        }
        for c in options
    ]


@dataclass(frozen=True, kw_only=True)
class MvgSensorDescription(SensorEntityDescription):
    value_fn: Callable[[list[Connection], datetime], Any]
    attrs_fn: Callable[[list[Connection]], dict[str, Any]] | None = None
    tick: bool = False  # recompute every minute between API updates


SENSORS = (
    MvgSensorDescription(
        key="leave_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda o, now: o[0].leave_at if o else None,
        attrs_fn=lambda o: {"options": _options(o)},
    ),
    MvgSensorDescription(
        key="minutes_until_leave",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda o, now: max(0, _minutes(o[0].leave_at - now)) if o else None,
        tick=True,
    ),
    MvgSensorDescription(
        key="arrival",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda o, now: o[0].arrival if o else None,
    ),
    MvgSensorDescription(
        key="transfer_wait",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda o, now: (
            min(_minutes(w) for w in o[0].transfer_waits) if o and o[0].transfer_waits else None
        ),
    ),
    MvgSensorDescription(
        key="route",
        value_fn=lambda o, now: o[0].summary if o else None,
        attrs_fn=lambda o: {"legs": _legs(o[0])} if o else {},
    ),
    MvgSensorDescription(
        key="next_leave_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda o, now: o[1].leave_at if len(o) > 1 else None,
        attrs_fn=lambda o: {"route": o[1].summary, "arrival": o[1].arrival.isoformat()}
        if len(o) > 1
        else {},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MvgCommuteConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(MvgCommuteSensor(coordinator, entry, d) for d in SENSORS)


class MvgCommuteSensor(MvgCommuteEntity, SensorEntity):
    entity_description: MvgSensorDescription

    def __init__(self, coordinator, entry, description: MvgSensorDescription) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.entity_description.tick:
            self.async_on_remove(
                async_track_time_interval(self.hass, self._tick, timedelta(minutes=1))
            )

    @callback
    def _tick(self, _now: datetime) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data or [], dt_util.utcnow())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attrs_fn
        return fn(self.coordinator.data or []) if fn else None
