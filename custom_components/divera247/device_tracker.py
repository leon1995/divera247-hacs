"""Device tracker platform for DIVERA vehicles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription

from custom_components.divera247.const import DOMAIN
from custom_components.divera247.entity import Divera247Entity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from custom_components.divera247.coordinator import Divera247DataUpdateCoordinator
    from custom_components.divera247.data import Divera247ConfigEntry
    from divera247.models.pull import VehicleStatusItem


@dataclass(frozen=True, kw_only=True)
class _VehicleTrackerDescription(EntityDescription):
    """Entity description for vehicle trackers."""


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: Divera247ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one tracker per vehicle from ``pull/vehicle-status``."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        Divera247VehicleTracker(
            coordinator=coordinator,
            vehicle_id=vehicle_id,
            description=_VehicleTrackerDescription(
                key=f"vehicle_{vehicle_id}_location",
                translation_key="vehicle_location",
            ),
        )
        for vehicle_id in coordinator.vehicle_status_by_id
    )


class Divera247VehicleTracker(Divera247Entity, TrackerEntity):
    """Tracker entity exposing the current position of a DIVERA vehicle."""

    _attr_has_entity_name = True
    _attr_translation_key = "vehicle_location"
    _attr_device_info: DeviceInfo | None = None

    def __init__(
        self,
        coordinator: Divera247DataUpdateCoordinator,
        vehicle_id: str,
        description: _VehicleTrackerDescription,
    ) -> None:
        """Initialize tracker entity."""
        super().__init__(coordinator, description)
        self._vehicle_id = vehicle_id
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{description.key}_{vehicle_id}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={
                (DOMAIN, f"{coordinator.config_entry.entry_id}_vehicle_{vehicle_id}")
            },
            manufacturer="DIVERA GmbH",
            name=f"Vehicle {vehicle_id}",
            via_device=(DOMAIN, coordinator.config_entry.entry_id),
        )

    @property
    def _vehicle(self) -> VehicleStatusItem | None:
        return self.coordinator.vehicle_status_by_id.get(self._vehicle_id)

    @property
    def name(self) -> str:
        """Return a human-readable name."""
        vehicle = self._vehicle
        if vehicle is None:
            return f"Vehicle {self._vehicle_id}"
        return vehicle.name or vehicle.shortname or f"Vehicle {self._vehicle_id}"

    @property
    def latitude(self) -> float | None:
        """Return latitude."""
        vehicle = self._vehicle
        return vehicle.lat if vehicle else None

    @property
    def longitude(self) -> float | None:
        """Return longitude."""
        vehicle = self._vehicle
        return vehicle.lng if vehicle else None

    @property
    def source_type(self) -> SourceType:
        """Return tracker source type."""
        return SourceType.GPS

    @property
    def extra_state_attributes(
        self,
    ) -> dict[str, Any]:
        """Return additional vehicle metadata."""
        vehicle = self._vehicle
        if vehicle is None:
            return {"vehicle_id": self._vehicle_id}
        return {
            "vehicle_id": vehicle.id,
            "fmsstatus_id": vehicle.fmsstatus_id,
            "fmsstatus_note": vehicle.fmsstatus_note,
            "fmsstatus_ts": vehicle.fmsstatus_ts,
        }
