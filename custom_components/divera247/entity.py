"""Base entity for the DIVERA 24/7 integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.divera247.const import ATTRIBUTION, DOMAIN, MANUFACTURER

if TYPE_CHECKING:
    from homeassistant.helpers.entity import EntityDescription

    from custom_components.divera247.coordinator import Divera247DataUpdateCoordinator


class Divera247Entity(CoordinatorEntity["Divera247DataUpdateCoordinator"]):
    """Base class for all DIVERA entities, grouped under one device."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Divera247DataUpdateCoordinator,
        entity_description: EntityDescription,
    ) -> None:
        """Initialise the entity with a device tied to the config entry."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{entity_description.key}"

        device_name = coordinator.config_entry.title or "DIVERA 24/7"
        cluster = coordinator.data.cluster if coordinator.data else None
        model = cluster.name if cluster and cluster.name else None

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=device_name,
            manufacturer=MANUFACTURER,
            model=model,
            configuration_url="https://app.divera247.com/",
        )
