"""
DataUpdateCoordinator for DIVERA 24/7.

The coordinator fetches the full ``/api/v2/pull/all`` payload at a fixed
interval and exposes it to all entity platforms. The raw Pydantic response
object is kept as ``coordinator.data`` so entities can navigate the nested
structure (``data.status``, ``data.cluster.status`` etc.) without another
layer of conversion.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from custom_components.divera247.api import Divera247ApiAuthError, Divera247ApiError
from custom_components.divera247.const import LOGGER

if TYPE_CHECKING:
    from custom_components.divera247.data import Divera247ConfigEntry
    from divera247.models.pull import PullData, VehicleStatusItem


class Divera247DataUpdateCoordinator(DataUpdateCoordinator["PullData | None"]):
    """Coordinator that keeps the DIVERA pull payload up to date."""

    config_entry: Divera247ConfigEntry
    vehicle_status_by_id: dict[str, VehicleStatusItem]

    async def _async_update_data(self) -> PullData | None:
        """Fetch the latest pull payload."""
        client = self.config_entry.runtime_data.client
        try:
            response = await client.async_get_pull_all()
        except Divera247ApiAuthError as exc:
            raise ConfigEntryAuthFailed(str(exc)) from exc
        except Divera247ApiError as exc:
            raise UpdateFailed(str(exc)) from exc

        if not response.success:
            msg = "DIVERA 24/7 API reported success=false"
            LOGGER.warning(msg)
            raise UpdateFailed(msg)
        if response.data is None:
            msg = "DIVERA pull/all returned no data"
            raise UpdateFailed(msg)

        try:
            vehicle_status = await client.async_get_vehicle_status()
        except Divera247ApiError as exc:
            if not self.vehicle_status_by_id:
                msg = "Vehicle status refresh failed during initial setup"
                raise UpdateFailed(msg) from exc
            LOGGER.debug(
                "Vehicle status refresh failed, keeping previous cache: %s",
                exc,
            )
        else:
            if not vehicle_status.success:
                if not self.vehicle_status_by_id:
                    msg = "DIVERA vehicle-status API reported success=false"
                    raise UpdateFailed(msg)
                LOGGER.warning(
                    "DIVERA vehicle-status API reported success=false; "
                    "keeping previous cache"
                )
            else:
                self.vehicle_status_by_id = {
                    str(item.id): item
                    for item in vehicle_status.data
                    if item.id is not None
                }

        return response.data
