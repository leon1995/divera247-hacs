"""Constants for the DIVERA 24/7 integration."""

from __future__ import annotations

from logging import Logger, getLogger
from typing import Final

LOGGER: Logger = getLogger(__package__)

DOMAIN: Final = "divera247"
MANUFACTURER: Final = "DIVERA GmbH"

CONF_ACCESS_KEY: Final = "access_key"

DEFAULT_SCAN_INTERVAL_SECONDS: Final = 900

ATTRIBUTION: Final = "Data provided by DIVERA 24/7"

SERVICE_SET_STATUS: Final = "set_status"
ATTR_STATUS_ID: Final = "status_id"
ATTR_NOTE: Final = "note"
ATTR_VEHICLE_ID: Final = "vehicle_id"
