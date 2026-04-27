"""Tests for binary sensor platform."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from custom_components.divera247.binary_sensor import (
    BINARY_SENSORS,
    Divera247BinarySensor,
    _active_alarm_attrs,
    _alarm_payload,
    _has_active_alarm,
    _sorted_alarms,
    _status_reset_scheduled,
    async_setup_entry,
)


class FakeModel:
    """Small model-like helper with model_dump support."""

    def __init__(self, **values: object) -> None:
        """Store arbitrary attributes for tests."""
        self.__dict__.update(values)

    def model_dump(self, mode: str = "json") -> dict[str, object]:  # noqa: ARG002
        """Return dict payload similar to Pydantic models."""
        return dict(self.__dict__)


def _coordinator(data: object | None) -> SimpleNamespace:
    if data is not None and not hasattr(data, "cluster"):
        data.cluster = SimpleNamespace(name="Cluster")
    return SimpleNamespace(
        data=data, config_entry=SimpleNamespace(entry_id="x", title="x")
    )


def test_alarm_helpers() -> None:
    """Cover alarm helper functions and ordering behavior."""
    a1 = FakeModel(id=1, closed=False)
    a2 = FakeModel(id=2, closed=True)
    data = SimpleNamespace(
        alarm=SimpleNamespace(items={"1": a1, "2": a2}, sorting=[1, 2])
    )
    assert _has_active_alarm(data) is True
    assert _alarm_payload(a1)["id"] == 1
    assert [a.id for a in _sorted_alarms(data)] == [1, 2]
    attrs = _active_alarm_attrs(data)
    assert attrs["open_alarm_count"] == 1
    assert attrs["open_alarm_ids"] == [1]

    empty = SimpleNamespace(alarm=None)
    assert _has_active_alarm(empty) is False
    assert _sorted_alarms(empty) == []

    unsorted = SimpleNamespace(alarm=SimpleNamespace(items={"1": a1}, sorting=[]))
    assert _sorted_alarms(unsorted) == [a1]


def test_status_reset_scheduled() -> None:
    """Return True only for numeric status reset timestamps."""
    assert _status_reset_scheduled(SimpleNamespace(status=None)) is False
    assert (
        _status_reset_scheduled(
            SimpleNamespace(status=SimpleNamespace(status_reset_date=None))
        )
        is False
    )
    assert (
        _status_reset_scheduled(
            SimpleNamespace(status=SimpleNamespace(status_reset_date=1))
        )
        is True
    )
    assert (
        _status_reset_scheduled(
            SimpleNamespace(status=SimpleNamespace(status_reset_date="12"))
        )
        is True
    )
    assert (
        _status_reset_scheduled(
            SimpleNamespace(status=SimpleNamespace(status_reset_date="x"))
        )
        is False
    )


def test_binary_sensor_entity_properties() -> None:
    """Entity exposes state and attributes from coordinator data."""
    data = SimpleNamespace(
        alarm=SimpleNamespace(items={"1": FakeModel(id=1, closed=False)}, sorting=[1])
    )
    coordinator = _coordinator(data)
    entity = Divera247BinarySensor(coordinator, BINARY_SENSORS[0])
    assert entity.is_on is True
    assert entity.extra_state_attributes is not None
    coordinator.data = None
    assert entity.is_on is None
    assert entity.extra_state_attributes is None


@pytest.mark.anyio
async def test_async_setup_entry_adds_entities() -> None:
    """Platform setup registers binary sensor entities."""
    coordinator = _coordinator(None)
    entry = SimpleNamespace(runtime_data=SimpleNamespace(coordinator=coordinator))
    add = Mock()
    await async_setup_entry(SimpleNamespace(), entry, add)
    assert add.call_count == 1
