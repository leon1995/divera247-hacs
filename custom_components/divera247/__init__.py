"""
The DIVERA 24/7 integration.

Sets up a single :class:`Divera247DataUpdateCoordinator` per config entry that
polls ``/api/v2/pull/all`` and fans the result out to sensor, binary_sensor
and select platforms. Also registers the ``divera247.set_status`` service.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.const import Platform
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.loader import async_get_loaded_integration

from custom_components.divera247.api import (
    Divera247ApiAuthError,
    Divera247ApiClient,
    Divera247ApiError,
)
from custom_components.divera247.const import (
    ATTR_NOTE,
    ATTR_STATUS_ID,
    ATTR_VEHICLE_ID,
    CONF_ACCESS_KEY,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    LOGGER,
    SERVICE_SET_STATUS,
)
from custom_components.divera247.coordinator import Divera247DataUpdateCoordinator
from custom_components.divera247.data import Divera247RuntimeData
from custom_components.divera247.websocket import Divera247WebSocketListener

if TYPE_CHECKING:
    from collections.abc import Sequence

    from homeassistant.core import HomeAssistant, ServiceCall

    from custom_components.divera247.data import Divera247ConfigEntry
    from divera247.models.pull import PullData

PLATFORMS: Sequence[Platform] = (
    Platform.BINARY_SENSOR,
    Platform.CALENDAR,
    Platform.DEVICE_TRACKER,
    Platform.SELECT,
    Platform.SENSOR,
)

SET_STATUS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_STATUS_ID): vol.Coerce(int),
        vol.Optional(ATTR_NOTE): cv.string,
        vol.Optional(ATTR_VEHICLE_ID): vol.Coerce(int),
    },
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Divera247ConfigEntry,
) -> bool:
    """Set up a DIVERA 24/7 config entry."""
    client = await hass.async_add_executor_job(
        Divera247ApiClient,
        entry.data[CONF_ACCESS_KEY],
    )

    coordinator = Divera247DataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,
        name=DOMAIN,
        update_interval=datetime.timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS),
    )
    entry.runtime_data = Divera247RuntimeData(
        client=client,
        coordinator=coordinator,
        integration=async_get_loaded_integration(hass, entry.domain),
    )

    await coordinator.async_config_entry_first_refresh()
    _async_update_entry_title(hass, entry, coordinator.data)

    ucr_id: int | None = None
    if coordinator.data is not None:
        ucr_id = coordinator.data.ucr_active or coordinator.data.ucr_default

    listener = Divera247WebSocketListener(
        hass=hass,
        coordinator=coordinator,
        api_client=client,
        ucr_id=ucr_id,
    )
    entry.runtime_data.ws_listener = listener
    listener.async_start()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _async_register_services(hass)

    return True


def _async_update_entry_title(
    hass: HomeAssistant,
    entry: Divera247ConfigEntry,
    data: PullData | None,
) -> None:
    """Align entry title with cluster/UCR-based naming."""
    if data is None:
        return
    cluster = data.cluster
    cluster_name = cluster.name if cluster is not None and cluster.name else "Unbekannt"
    title_base = cluster_name.strip()
    if not title_base.casefold().startswith("feuerwehr"):
        title_base = f"Feuerwehr {title_base}"
    ucr_id = data.ucr_active or data.ucr_default
    new_title = (
        f"{title_base} {ucr_id}"
        if ucr_id is not None
        else title_base
    )
    if entry.title != new_title:
        hass.config_entries.async_update_entry(entry, title=new_title)


async def async_unload_entry(
    hass: HomeAssistant,
    entry: Divera247ConfigEntry,
) -> bool:
    """Unload a DIVERA 24/7 config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        runtime = entry.runtime_data
        if runtime.ws_listener is not None:
            await runtime.ws_listener.async_stop()
        await runtime.client.async_close()
    return unloaded


async def async_reload_entry(
    hass: HomeAssistant,
    entry: Divera247ConfigEntry,
) -> None:
    """Reload the config entry (e.g. after options change)."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_register_services(hass: HomeAssistant) -> None:
    """Register the ``divera247.set_status`` service (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_STATUS):
        return

    async def _handle_set_status(call: ServiceCall) -> None:
        """
        Forward the service call to the first loaded DIVERA entry.

        DIVERA supports only one user per access key, so looking up any
        loaded config entry is enough to dispatch the call.
        """
        entries = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if getattr(entry, "runtime_data", None) is not None
        ]
        if not entries:
            msg = "No loaded DIVERA 24/7 integration found"
            raise HomeAssistantError(msg)

        entry = entries[0]
        runtime = entry.runtime_data
        try:
            await runtime.client.async_set_status(
                status_id=call.data[ATTR_STATUS_ID],
                note=call.data.get(ATTR_NOTE),
                vehicle_id=call.data.get(ATTR_VEHICLE_ID),
            )
        except Divera247ApiAuthError as exc:
            msg = f"DIVERA auth failed: {exc}"
            raise HomeAssistantError(msg) from exc
        except Divera247ApiError as exc:
            msg = f"DIVERA API error: {exc}"
            raise HomeAssistantError(msg) from exc
        await runtime.coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_STATUS,
        _handle_set_status,
        schema=SET_STATUS_SCHEMA,
    )
