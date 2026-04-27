"""Tests for calendar platform."""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from homeassistant.components.calendar import CalendarEntityDescription

from custom_components.divera247.calendar import (
    Divera247EventsCalendar,
    _event_start,
    _to_calendar_event,
    async_setup_entry,
)


def _coordinator(data: object | None) -> SimpleNamespace:
    if data is not None and not hasattr(data, "cluster"):
        data.cluster = SimpleNamespace(name="Cluster")
    return SimpleNamespace(
        data=data, config_entry=SimpleNamespace(entry_id="x", title="x")
    )


def test_event_start_and_conversion() -> None:
    """Convert event timestamps and build calendar events."""
    now = datetime.datetime.now(tz=datetime.UTC)
    event = SimpleNamespace(id=1, date=now, title="A", text="B", address="C")
    assert _event_start(event) == now
    cal = _to_calendar_event(event)
    assert cal is not None
    assert cal.summary == "A"
    assert (
        _to_calendar_event(
            SimpleNamespace(id=2, date=None, title=None, text=None, address=None)
        )
        is None
    )
    ts_event = SimpleNamespace(
        id=3, date=1700000000, title=None, text=None, address=None
    )
    assert _event_start(ts_event) == datetime.datetime.fromtimestamp(
        1700000000, tz=datetime.UTC
    )


def test_calendar_entity_events_and_current() -> None:
    """Expose next upcoming event and handle empty/invalid data."""
    now = datetime.datetime.now(tz=datetime.UTC)
    old = SimpleNamespace(
        id=1, date=now - datetime.timedelta(days=1), title="Old", text="", address=""
    )
    new = SimpleNamespace(
        id=2, date=now + datetime.timedelta(hours=1), title="New", text="", address=""
    )
    data = SimpleNamespace(events=SimpleNamespace(items={"1": new, "2": old}))
    entity = Divera247EventsCalendar(
        _coordinator(data), CalendarEntityDescription(key="events")
    )
    assert entity.event is not None
    assert entity.event.summary == "New"

    empty = Divera247EventsCalendar(
        _coordinator(SimpleNamespace(events=None)),
        CalendarEntityDescription(key="events"),
    )
    assert empty.event is None

    invalid = SimpleNamespace(
        events=SimpleNamespace(
            items={
                "1": SimpleNamespace(
                    id=1, date=None, title="NoDate", text="", address=""
                ),
                "2": SimpleNamespace(id=2, date=0, title="Epoch", text="", address=""),
            }
        )
    )
    invalid_entity = Divera247EventsCalendar(
        _coordinator(invalid), CalendarEntityDescription(key="events")
    )
    assert invalid_entity.event is None


@pytest.mark.anyio
async def test_calendar_get_events_and_setup() -> None:
    """Filter events by range and verify platform setup."""
    now = datetime.datetime.now(tz=datetime.UTC)
    ev1 = SimpleNamespace(id=1, date=now, title="A", text="", address="")
    ev2 = SimpleNamespace(
        id=2, date=now + datetime.timedelta(days=10), title="B", text="", address=""
    )
    data = SimpleNamespace(events=SimpleNamespace(items={"1": ev1, "2": ev2}))
    entity = Divera247EventsCalendar(
        _coordinator(data), CalendarEntityDescription(key="events")
    )
    events = await entity.async_get_events(
        SimpleNamespace(),
        now - datetime.timedelta(days=1),
        now + datetime.timedelta(days=1),
    )
    assert len(events) == 1
    assert events[0].summary == "A"

    invalid_entity = Divera247EventsCalendar(
        _coordinator(
            SimpleNamespace(
                events=SimpleNamespace(
                    items={
                        "x": SimpleNamespace(
                            id=99, date=None, title="x", text="", address=""
                        )
                    }
                )
            )
        ),
        CalendarEntityDescription(key="events"),
    )
    assert (
        await invalid_entity.async_get_events(
            SimpleNamespace(),
            now - datetime.timedelta(days=1),
            now + datetime.timedelta(days=1),
        )
        == []
    )

    add = Mock()
    entry = SimpleNamespace(
        runtime_data=SimpleNamespace(coordinator=_coordinator(data))
    )
    await async_setup_entry(SimpleNamespace(), entry, add)
    assert add.call_count == 1
