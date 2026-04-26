"""Select platform for changing the current DIVERA user status."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.exceptions import HomeAssistantError

from custom_components.divera247.api import Divera247ApiAuthError, Divera247ApiError
from custom_components.divera247.const import LOGGER
from custom_components.divera247.entity import Divera247Entity

if TYPE_CHECKING:
    from collections.abc import Sequence

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from custom_components.divera247.coordinator import Divera247DataUpdateCoordinator
    from custom_components.divera247.data import Divera247ConfigEntry
    from divera247.models.pull import PullData, PullStatusDefinitionData


STATUS_DESCRIPTION = SelectEntityDescription(
    key="status_select",
    translation_key="status_select",
    icon="mdi:account-switch",
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: Divera247ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the select platform."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities([Divera247StatusSelect(coordinator)])


def _visible_status_definitions(
    data: PullData,
) -> Sequence[PullStatusDefinitionData]:
    """
    Return the status definitions that should be exposed to the user.

    The API flags each status with ``show_on_statusgeber``; we respect that
    so the Home Assistant dropdown mirrors what the user would see in the
    official app.
    """
    if data.cluster is None or not data.cluster.status:
        return []

    sorting = data.cluster.statussorting_statusgeber or data.cluster.statussorting
    status_map = {
        int(key): value
        for key, value in data.cluster.status.items()
        if key.lstrip("-").isdigit()
    }
    ordered_ids: Sequence[int]
    if sorting:
        ordered_ids = [sid for sid in sorting if sid in status_map]
    else:
        ordered_ids = sorted(status_map.keys())

    visible: list[PullStatusDefinitionData] = []
    for sid in ordered_ids:
        definition = status_map[sid]
        if definition.hidden:
            continue
        if definition.show_on_statusgeber is False:
            continue
        if not definition.name:
            continue
        visible.append(definition)
    return visible


class Divera247StatusSelect(Divera247Entity, SelectEntity):
    """Select entity that mirrors and updates the user's current status."""

    entity_description: SelectEntityDescription

    def __init__(self, coordinator: Divera247DataUpdateCoordinator) -> None:
        """Initialise the select entity."""
        super().__init__(coordinator, STATUS_DESCRIPTION)

    def _definitions(self) -> Sequence[PullStatusDefinitionData]:
        """Return the currently visible status definitions."""
        data = self.coordinator.data
        if data is None:
            return []
        return _visible_status_definitions(data)

    @property
    def options(self) -> list[str]:
        """Return the selectable status names."""
        return [d.name for d in self._definitions() if d.name]

    @property
    def current_option(self) -> str | None:
        """Return the name of the currently set status, or ``None``."""
        data = self.coordinator.data
        if data is None or data.status is None or data.status.status_id is None:
            return None
        for definition in self._definitions():
            if definition.id == data.status.status_id:
                return definition.name
        return None

    async def async_select_option(self, option: str) -> None:
        """Change the user status by name."""
        for definition in self._definitions():
            if definition.name == option and definition.id is not None:
                client = self.coordinator.config_entry.runtime_data.client
                try:
                    await client.async_set_status(status_id=definition.id)
                except Divera247ApiAuthError as exc:
                    msg = f"DIVERA auth failed: {exc}"
                    raise HomeAssistantError(
                        msg,
                    ) from exc
                except Divera247ApiError as exc:
                    msg = f"DIVERA API error: {exc}"
                    raise HomeAssistantError(
                        msg,
                    ) from exc
                await self.coordinator.async_request_refresh()
                return

        LOGGER.warning("Unknown DIVERA status option selected: %s", option)
        msg = f"Unknown DIVERA status option: {option}"
        raise HomeAssistantError(msg)
