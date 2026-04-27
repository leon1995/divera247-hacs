"""Tests for device tracker platform."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from homeassistant.components.device_tracker import SourceType

from custom_components.divera247.device_tracker import (
    Divera247VehicleTracker,
    _VehicleTrackerDescription,
    async_setup_entry,
)


def _coordinator() -> SimpleNamespace:
    return SimpleNamespace(
        data=None,
        config_entry=SimpleNamespace(entry_id="entry", title="title"),
        vehicle_status_by_id={
            "1": SimpleNamespace(
                id=1,
                name="HLF",
                shortname="H1",
                lat=1.1,
                lng=2.2,
                fmsstatus_id=3,
                fmsstatus_note="note",
                fmsstatus_ts=None,
            )
        },
    )


def test_tracker_properties() -> None:
    """Expose name, coordinates, source type, and attributes."""
    desc = _VehicleTrackerDescription(key="k", translation_key="vehicle_location")
    tracker = Divera247VehicleTracker(_coordinator(), "1", desc)
    assert tracker.name == "HLF"
    assert tracker.latitude == 1.1
    assert tracker.longitude == 2.2
    assert tracker.source_type == SourceType.GPS
    assert tracker.extra_state_attributes["vehicle_id"] == 1

    missing = Divera247VehicleTracker(_coordinator(), "99", desc)
    assert missing.name == "Vehicle 99"
    assert missing.latitude is None
    assert missing.longitude is None
    assert missing.extra_state_attributes == {"vehicle_id": "99"}


@pytest.mark.anyio
async def test_setup_entry_adds_vehicle_trackers() -> None:
    """Platform setup adds one tracker per vehicle."""
    add = Mock()
    coordinator = _coordinator()
    entry = SimpleNamespace(runtime_data=SimpleNamespace(coordinator=coordinator))
    await async_setup_entry(SimpleNamespace(), entry, add)
    assert add.call_count == 1
