"""
Sensor platform for DIVERA 24/7.

Exposes operational state from the ``pull/all`` payload, including status,
alarm/news/event summaries, scheduling data and diagnostic metadata.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)

from custom_components.divera247.entity import Divera247Entity

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from custom_components.divera247.coordinator import Divera247DataUpdateCoordinator
    from custom_components.divera247.data import Divera247ConfigEntry
    from divera247.models.alarm import AlarmResult
    from divera247.models.event import EventResult
    from divera247.models.news import NewsResult
    from divera247.models.pull import PullData


def _timestamp(
    ts: int | float | str | datetime.datetime | None,
) -> datetime.datetime | None:
    if ts is None:
        return None
    if isinstance(ts, datetime.datetime):
        if ts.tzinfo is not None:
            return ts
        return ts.replace(tzinfo=datetime.UTC)
    if isinstance(ts, str):
        ts = ts.strip()
        if not ts:
            return None
        if ts.isdigit():
            ts = int(ts)
        else:
            return None
    return datetime.datetime.fromtimestamp(ts, tz=datetime.UTC)


def _status_name(data: PullData) -> str | None:
    if data.status is None or data.status.status_id is None or data.cluster is None:
        return None
    definition = data.cluster.status.get(str(data.status.status_id))
    return definition.name if definition and definition.name else None


def _status_note(data: PullData) -> str | None:
    return data.status.note if data.status else None


def _status_set_date(data: PullData) -> datetime.datetime | None:
    if data.status is None:
        return None
    return _timestamp(data.status.status_set_date)


def _next_status_reset(data: PullData) -> datetime.datetime | None:
    if data.status is None:
        return None
    ts = data.status.status_reset_date
    if isinstance(ts, int):
        return _timestamp(ts)
    if isinstance(ts, str) and ts.isdigit():
        return _timestamp(int(ts))
    return None


def _new_alarms(data: PullData) -> int | None:
    return data.alarm.new if data.alarm else None


def _new_messages(data: PullData) -> int | None:
    return data.news.new if data.news else None


def _items_sorted(
    items: Mapping[str, Any] | None,
    sorting: Sequence[int] | None,
) -> Sequence[Any]:
    if not items:
        return []
    if not sorting:
        return list(items.values())
    ordered: list[Any] = []
    for item_id in sorting:
        item = items.get(str(item_id))
        if item is not None:
            ordered.append(item)
    return ordered


def _latest_alarm(data: PullData) -> AlarmResult | None:
    if data.alarm is None:
        return None
    alarms = _items_sorted(data.alarm.items, data.alarm.sorting)
    return alarms[-1] if alarms else None


def _latest_news(data: PullData) -> NewsResult | None:
    if data.news is None:
        return None
    news = _items_sorted(data.news.items, data.news.sorting)
    return news[-1] if news else None


def _next_event(data: PullData) -> EventResult | None:
    if data.events is None or not data.events.items:
        return None
    now_ts = datetime.datetime.now(tz=datetime.UTC)
    candidates = [
        event
        for event in data.events.items.values()
        if (event_date := _timestamp(event.date)) is not None and event_date >= now_ts
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda event: _timestamp(event.date) or now_ts)


def _latest_alarm_title(data: PullData) -> str | None:
    alarm = _latest_alarm(data)
    return alarm.title if alarm else None


def _latest_alarm_location(data: PullData) -> str | None:
    alarm = _latest_alarm(data)
    if alarm is None:
        return None
    return alarm.address or alarm.destination_address


def _latest_alarm_time(data: PullData) -> datetime.datetime | None:
    alarm = _latest_alarm(data)
    if alarm is None:
        return None
    return _timestamp(alarm.date or alarm.ts_create or alarm.ts_update)


def _latest_alarm_attrs(data: PullData) -> Mapping[str, int | str | None]:
    """Return attributes for the latest alarm sensor."""
    alarm = _latest_alarm(data)
    if alarm is None:
        return {"alarm_id": None, "keyword": None}
    return {
        "alarm_id": alarm.id,
        "keyword": alarm.title,
    }


def _open_alarms(data: PullData) -> int | None:
    if data.alarm is None or not data.alarm.items:
        return 0
    return sum(1 for alarm in data.alarm.items.values() if alarm.closed is False)


def _user_fullname(data: PullData) -> str | None:
    if data.user is None:
        return None
    name = " ".join(
        part for part in (data.user.firstname, data.user.lastname) if part
    ).strip()
    return name or None


def _unit_name(data: PullData) -> str | None:
    return data.cluster.name if data.cluster else None


def _next_event_title(data: PullData) -> str | None:
    event = _next_event(data)
    return event.title if event else None


def _next_event_start(data: PullData) -> datetime.datetime | None:
    event = _next_event(data)
    if event is None:
        return None
    return _timestamp(event.date)


def _next_event_attrs(data: PullData) -> Mapping[str, str | int | None]:
    """Return attributes for the next event sensor."""
    event = _next_event(data)
    if event is None:
        return {"event_id": None, "start": None}
    start = _timestamp(event.date)
    return {
        "event_id": event.id,
        "start": start.isoformat() if start else None,
    }


def _access_bool(data: PullData, key: str) -> bool | None:
    if data.user is None:
        return None
    raw = data.user.access.get(key)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int):
        return raw > 0
    if isinstance(raw, str):
        return raw.lower() in {"1", "true", "yes", "on"}
    return None


@dataclass(frozen=True, kw_only=True)
class Divera247SensorEntityDescription(SensorEntityDescription):
    """Describe a DIVERA sensor and how to derive its state from pull data."""

    value_fn: Callable[[PullData], Any]
    attrs_fn: Callable[[PullData], Mapping[str, Any]] | None = None


SENSORS: Sequence[Divera247SensorEntityDescription] = (
    Divera247SensorEntityDescription(
        key="status",
        translation_key="status",
        icon="mdi:account-alert",
        value_fn=_status_name,
        attrs_fn=lambda data: {
            "status_id": data.status.status_id if data.status else None,
            "note": _status_note(data),
            "vehicle_id": data.status.vehicle if data.status else None,
        },
    ),
    Divera247SensorEntityDescription(
        key="status_id",
        translation_key="status_id",
        icon="mdi:numeric",
        value_fn=lambda data: data.status.status_id if data.status else None,
    ),
    Divera247SensorEntityDescription(
        key="status_note",
        translation_key="status_note",
        icon="mdi:note-text-outline",
        value_fn=_status_note,
    ),
    Divera247SensorEntityDescription(
        key="status_vehicle_id",
        translation_key="status_vehicle_id",
        icon="mdi:fire-truck",
        value_fn=lambda data: data.status.vehicle if data.status else None,
    ),
    Divera247SensorEntityDescription(
        key="status_changed",
        translation_key="status_changed",
        icon="mdi:clock-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_status_set_date,
    ),
    Divera247SensorEntityDescription(
        key="next_status_reset",
        translation_key="next_status_reset",
        icon="mdi:calendar-clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_next_status_reset,
    ),
    Divera247SensorEntityDescription(
        key="new_alarms",
        translation_key="new_alarms",
        icon="mdi:alarm-light",
        native_unit_of_measurement="alarms",
        value_fn=_new_alarms,
    ),
    Divera247SensorEntityDescription(
        key="open_alarms",
        translation_key="open_alarms",
        icon="mdi:alarm",
        native_unit_of_measurement="alarms",
        value_fn=_open_alarms,
    ),
    Divera247SensorEntityDescription(
        key="latest_alarm",
        translation_key="latest_alarm",
        icon="mdi:alarm-light-outline",
        value_fn=_latest_alarm_title,
        attrs_fn=_latest_alarm_attrs,
    ),
    Divera247SensorEntityDescription(
        key="latest_alarm_time",
        translation_key="latest_alarm_time",
        icon="mdi:clock-alert-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_latest_alarm_time,
    ),
    Divera247SensorEntityDescription(
        key="latest_alarm_location",
        translation_key="latest_alarm_location",
        icon="mdi:map-marker-alert-outline",
        value_fn=_latest_alarm_location,
    ),
    Divera247SensorEntityDescription(
        key="new_messages",
        translation_key="new_messages",
        icon="mdi:message-badge",
        native_unit_of_measurement="messages",
        value_fn=_new_messages,
    ),
    Divera247SensorEntityDescription(
        key="next_event",
        translation_key="next_event",
        icon="mdi:calendar-star",
        value_fn=_next_event_title,
        attrs_fn=_next_event_attrs,
    ),
    Divera247SensorEntityDescription(
        key="next_event_start",
        translation_key="next_event_start",
        icon="mdi:calendar-clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_next_event_start,
    ),
    Divera247SensorEntityDescription(
        key="user",
        translation_key="user",
        icon="mdi:account",
        value_fn=_user_fullname,
        entity_registry_enabled_default=False,
    ),
    Divera247SensorEntityDescription(
        key="unit",
        translation_key="unit",
        icon="mdi:home-group",
        value_fn=_unit_name,
        entity_registry_enabled_default=False,
    ),
    Divera247SensorEntityDescription(
        key="cluster_id",
        translation_key="cluster_id",
        icon="mdi:identifier",
        value_fn=lambda data: data.cluster.id if data.cluster else None,
        entity_registry_enabled_default=False,
    ),
    Divera247SensorEntityDescription(
        key="ucr_active",
        translation_key="ucr_active",
        icon="mdi:account-key-outline",
        value_fn=lambda data: data.ucr_active,
        entity_registry_enabled_default=False,
    ),
    Divera247SensorEntityDescription(
        key="ucr_default",
        translation_key="ucr_default",
        icon="mdi:account-star-outline",
        value_fn=lambda data: data.ucr_default,
        entity_registry_enabled_default=False,
    ),
    Divera247SensorEntityDescription(
        key="server_time",
        translation_key="server_time",
        icon="mdi:server-clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: _timestamp(data.ts),
        entity_registry_enabled_default=False,
    ),
    Divera247SensorEntityDescription(
        key="can_set_status",
        translation_key="can_set_status",
        icon="mdi:account-switch",
        value_fn=lambda data: _access_bool(data, "status_manual"),
        entity_registry_enabled_default=False,
    ),
    Divera247SensorEntityDescription(
        key="can_manage_alarms",
        translation_key="can_manage_alarms",
        icon="mdi:alarm-cog",
        value_fn=lambda data: _access_bool(data, "alarm"),
        entity_registry_enabled_default=False,
    ),
    Divera247SensorEntityDescription(
        key="can_send_messages",
        translation_key="can_send_messages",
        icon="mdi:message-cog",
        value_fn=lambda data: _access_bool(data, "messages"),
        entity_registry_enabled_default=False,
    ),
    Divera247SensorEntityDescription(
        key="can_manage_news",
        translation_key="can_manage_news",
        icon="mdi:newspaper-variant-outline",
        value_fn=lambda data: _access_bool(data, "news"),
        entity_registry_enabled_default=False,
    ),
    Divera247SensorEntityDescription(
        key="can_set_vehicle_status",
        translation_key="can_set_vehicle_status",
        icon="mdi:fire-truck-alert",
        value_fn=lambda data: _access_bool(data, "status_vehicle"),
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: Divera247ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        Divera247Sensor(coordinator, description) for description in SENSORS
    )


class Divera247Sensor(Divera247Entity, SensorEntity):
    """Single DIVERA sensor entity."""

    entity_description: Divera247SensorEntityDescription

    def __init__(
        self,
        coordinator: Divera247DataUpdateCoordinator,
        entity_description: Divera247SensorEntityDescription,
    ) -> None:
        """Initialise the sensor entity."""
        super().__init__(coordinator, entity_description)

    @property
    def native_value(self) -> Any:
        """Return the current value derived from the pull payload."""
        data = self.coordinator.data
        if data is None:
            return None
        return self.entity_description.value_fn(data)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return any extra attributes declared on the description."""
        data = self.coordinator.data
        if data is None or self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(data)
