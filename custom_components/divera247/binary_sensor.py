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
    from collections.abc import Callable, Sequence

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from custom_components.divera247.coordinator import Divera247DataUpdateCoordinator
    from custom_components.divera247.data import Divera247ConfigEntry
    from divera247.models.pull import PullData


def _has_active_alarm(data: PullData) -> bool:
    """Return ``True`` while at least one alarm is flagged as not closed."""
    if data.alarm is None or not data.alarm.items:
        return False
    return any(alarm.closed is False for alarm in data.alarm.items.values())


def _has_unread_alarm(data: PullData) -> bool:
    """Return ``True`` while at least one alarm is marked as unread/new."""
    if data.alarm is None or not data.alarm.items:
        return False
    return any(alarm.new for alarm in data.alarm.items.values())


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


BINARY_SENSORS: Sequence[Divera247BinarySensorEntityDescription] = (
    Divera247BinarySensorEntityDescription(
        key="active_alarm",
        translation_key="active_alarm",
        device_class=BinarySensorDeviceClass.SAFETY,
        value_fn=_has_active_alarm,
    ),
    Divera247BinarySensorEntityDescription(
        key="unread_alarm",
        translation_key="unread_alarm",
        icon="mdi:bell-alert",
        value_fn=_has_unread_alarm,
        entity_registry_enabled_default=False,
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
