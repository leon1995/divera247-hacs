"""Calendar platform exposing DIVERA events."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEntityDescription,
    CalendarEvent,
)

from custom_components.divera247.entity import Divera247Entity

if TYPE_CHECKING:
    from collections.abc import Sequence

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from custom_components.divera247.coordinator import Divera247DataUpdateCoordinator
    from custom_components.divera247.data import Divera247ConfigEntry
    from divera247.models.event import EventResult


def _event_start(event: EventResult) -> datetime.datetime | None:
    if event.date is None:
        return None
    if isinstance(event.date, datetime.datetime):
        return event.date
    return datetime.datetime.fromtimestamp(event.date, tz=datetime.UTC)


def _to_calendar_event(event: EventResult) -> CalendarEvent | None:
    start = _event_start(event)
    if start is None:
        return None
    end = start + datetime.timedelta(hours=1)
    return CalendarEvent(
        summary=event.title or f"Event {event.id}",
        description=event.text,
        start=start,
        end=end,
        location=event.address,
    )


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: Divera247ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the calendar platform."""
    async_add_entities(
        [
            Divera247EventsCalendar(
                entry.runtime_data.coordinator,
                CalendarEntityDescription(
                    key="events",
                    translation_key="events",
                ),
            )
        ]
    )


class Divera247EventsCalendar(Divera247Entity, CalendarEntity):
    """Single calendar entity containing all DIVERA events."""

    _attr_translation_key = "events"

    def __init__(
        self,
        coordinator: Divera247DataUpdateCoordinator,
        entity_description: CalendarEntityDescription,
    ) -> None:
        """Initialize the calendar entity."""
        super().__init__(coordinator, entity_description)

    def _events(self) -> Sequence[EventResult]:
        data = self.coordinator.data
        if data is None or data.events is None or not data.events.items:
            return []
        return sorted(
            data.events.items.values(),
            key=lambda event: event.date or 0,
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        now = datetime.datetime.now(tz=datetime.UTC)
        for source_event in self._events():
            calendar_event = _to_calendar_event(source_event)
            if calendar_event is None:
                continue
            if calendar_event.end >= now:
                return calendar_event
        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,  # noqa: ARG002
        start_date: datetime.datetime,
        end_date: datetime.datetime,
    ) -> list[CalendarEvent]:
        """Return events in the requested date range."""
        results: list[CalendarEvent] = []
        for source_event in self._events():
            event = _to_calendar_event(source_event)
            if event is None:
                continue
            if event.end < start_date or event.start > end_date:
                continue
            results.append(event)
        return results
