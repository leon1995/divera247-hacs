"""Custom runtime types for the DIVERA 24/7 integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from custom_components.divera247.api import Divera247ApiClient
    from custom_components.divera247.coordinator import Divera247DataUpdateCoordinator
    from custom_components.divera247.websocket import Divera247WebSocketListener


type Divera247ConfigEntry = ConfigEntry[Divera247RuntimeData]


@dataclass
class Divera247RuntimeData:
    """Runtime data attached to the config entry."""

    client: Divera247ApiClient
    coordinator: Divera247DataUpdateCoordinator
    integration: Integration
    ws_listener: Divera247WebSocketListener | None = None
