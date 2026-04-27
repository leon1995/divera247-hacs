"""Binary sensor platform for DIVERA 24/7."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)

from custom_components.divera247.entity import Divera247Entity

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from custom_components.divera247.coordinator import Divera247DataUpdateCoordinator
    from custom_components.divera247.data import Divera247ConfigEntry
    from divera247.models.alarm import AlarmResult
    from divera247.models.pull import PullData


def _has_active_alarm(data: PullData) -> bool:
    """Return ``True`` while at least one alarm is flagged as not closed."""
    if data.alarm is None or not data.alarm.items:
        return False
    return any(alarm.closed is False for alarm in data.alarm.items.values())


def _alarm_payload(alarm: AlarmResult) -> Mapping[str, object]:
    """Return a JSON-serializable dict for one alarm model."""
    return alarm.model_dump(mode="json")


def _sorted_alarms(data: PullData) -> Sequence[AlarmResult]:
    """Return alarm items in server-defined order when available."""
    if data.alarm is None or not data.alarm.items:
        return []
    if not data.alarm.sorting:
        return list(data.alarm.items.values())
    ordered: list[AlarmResult] = []
    for alarm_id in data.alarm.sorting:
        alarm = data.alarm.items.get(str(alarm_id))
        if alarm is not None:
            ordered.append(alarm)
    return ordered


def _active_alarm_attrs(data: PullData) -> Mapping[str, object]:
    """Return all open alarm details for the active alarm binary sensor."""
    alarms = [alarm for alarm in _sorted_alarms(data) if alarm.closed is False]
    return {
        "open_alarm_count": len(alarms),
        "open_alarm_ids": [alarm.id for alarm in alarms],
        "alarms": [_alarm_payload(alarm) for alarm in alarms],
    }


def _status_reset_scheduled(data: PullData) -> bool:
    """Return ``True`` if a future automatic status reset is scheduled."""
    if data.status is None or data.status.status_reset_date is None:
        return False
    ts = data.status.status_reset_date
    return isinstance(ts, int) or (isinstance(ts, str) and ts.isdigit())


@dataclass(frozen=True, kw_only=True)
class Divera247BinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describe a DIVERA binary sensor."""

    value_fn: Callable[[PullData], bool]
    attrs_fn: Callable[[PullData], Mapping[str, object]] | None = None


BINARY_SENSORS: Sequence[Divera247BinarySensorEntityDescription] = (
    Divera247BinarySensorEntityDescription(
        key="active_alarm",
        translation_key="active_alarm",
        device_class=BinarySensorDeviceClass.SAFETY,
        value_fn=_has_active_alarm,
        attrs_fn=_active_alarm_attrs,
    ),
    Divera247BinarySensorEntityDescription(
        key="status_reset_scheduled",
        translation_key="status_reset_scheduled",
        icon="mdi:calendar-sync",
        value_fn=_status_reset_scheduled,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: Divera247ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        Divera247BinarySensor(coordinator, description)
        for description in BINARY_SENSORS
    )


class Divera247BinarySensor(Divera247Entity, BinarySensorEntity):
    """Single DIVERA binary sensor entity."""

    entity_description: Divera247BinarySensorEntityDescription

    def __init__(
        self,
        coordinator: Divera247DataUpdateCoordinator,
        entity_description: Divera247BinarySensorEntityDescription,
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, entity_description)

    @property
    def is_on(self) -> bool | None:
        """Return the evaluated state of the binary sensor."""
        data = self.coordinator.data
        if data is None:
            return None
        return self.entity_description.value_fn(data)

    @property
    def extra_state_attributes(self) -> Mapping[str, object] | None:
        """Return optional binary sensor attributes from pull data."""
        data = self.coordinator.data
        if data is None or self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(data)
