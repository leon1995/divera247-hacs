"""
Sensor platform for DIVERA 24/7.

Exposes operational state from the ``pull/all`` payload, including status,
alarm/news/event summaries, scheduling data and diagnostic metadata.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.helpers.entity import EntityCategory

from custom_components.divera247.entity import Divera247Entity
from divera247.models.event import EventResult

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from custom_components.divera247.coordinator import Divera247DataUpdateCoordinator
    from custom_components.divera247.data import Divera247ConfigEntry
    from divera247.models.alarm import AlarmResult
    from divera247.models.pull import PullData, VehicleStatusItem


def _timestamp(
    ts: float | str | datetime.datetime | None,
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


def _status_attrs(data: PullData) -> Mapping[str, object]:
    """Return full status payload plus compatibility aliases."""
    if data.status is None:
        return {"status_id": None, "note": None, "vehicle_id": None}
    return data.status.model_dump(mode="json")


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


def _items_sorted[T](
    items: Mapping[str, T] | None,
    sorting: Sequence[int] | None,
) -> Sequence[T]:
    if not items:
        return []
    if not sorting:
        return list(items.values())
    ordered: list[T] = []
    for item_id in sorting:
        item = items.get(str(item_id))
        if item is not None:
            ordered.append(item)
    return ordered


def _latest_alarm(data: PullData) -> AlarmResult | None:
    if data.alarm is None:
        return None
    alarms = _items_sorted(data.alarm.items, data.alarm.sorting)
    return alarms[0] if alarms else None


def _all_alarm_items(data: PullData) -> Sequence[AlarmResult]:
    """Return all alarms in API-defined order."""
    if data.alarm is None:
        return []
    return _items_sorted(data.alarm.items, data.alarm.sorting)


def _all_alarms_count(data: PullData) -> int:
    """Return number of alarms in current pull payload."""
    return len(_all_alarm_items(data))


def _next_event(data: PullData) -> EventResult | None:
    if data.events is None or not data.events.items:
        return None
    now_ts = datetime.datetime.now(tz=datetime.UTC)
    candidates = [
        event
        for event in data.events.items.values()
        if (
            ((event_end := event.end) is not None and event_end >= now_ts)
            or (
                event.end is None
                and (event_start := event.start) is not None
                and event_start >= now_ts
            )
        )
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda event: event.start or event.end or now_ts)


def _latest_alarm_title(data: PullData) -> str | None:
    alarm = _latest_alarm(data)
    return alarm.title if alarm else None


def _latest_alarm_attrs(data: PullData) -> Mapping[str, object]:
    """Return attributes for the latest alarm sensor."""
    alarm = _latest_alarm(data)
    if alarm is None:
        return {}
    payload = dict(alarm.model_dump(mode="json"))
    payload.setdefault("alarm_id", payload.get("id"))
    payload.setdefault("keyword", payload.get("title"))
    self_status_id = payload.get("ucr_self_status_id")
    if isinstance(self_status_id, int) and data.cluster is not None:
        definition = data.cluster.status.get(str(self_status_id))
        payload["ucr_self_status_name"] = (
            definition.name if definition and definition.name else None
        )
    ucr_answered = payload.get("ucr_answered")
    if isinstance(ucr_answered, Mapping):
        payload["ucr_answered"] = _humanize_ucr_answered(data, ucr_answered)
    ucr_addressed = payload.get("ucr_addressed")
    if isinstance(ucr_addressed, Sequence) and not isinstance(ucr_addressed, str):
        payload["ucr_addressed"] = _humanize_ucr_user_list(data, ucr_addressed)
    ucr_adressed = payload.get("ucr_adressed")
    if isinstance(ucr_adressed, Sequence) and not isinstance(ucr_adressed, str):
        payload["ucr_adressed"] = _humanize_ucr_user_list(data, ucr_adressed)
    ucr_answeredcount = payload.get("ucr_answeredcount")
    if isinstance(ucr_answeredcount, Mapping):
        payload["ucr_answeredcount"] = _humanize_status_count_map(
            data,
            ucr_answeredcount,
        )
    ucr_read = payload.get("ucr_read")
    if isinstance(ucr_read, Sequence) and not isinstance(ucr_read, str):
        payload["ucr_read"] = _humanize_ucr_user_list(data, ucr_read)
    return payload


def _all_alarms_attrs(data: PullData) -> Mapping[str, object]:
    """Return normalized payload for all alarms."""
    alarms_payload: list[Mapping[str, object]] = []
    open_count = 0
    for alarm in _all_alarm_items(data):
        payload = dict(alarm.model_dump(mode="json"))
        payload.setdefault("alarm_id", payload.get("id"))
        payload.setdefault("keyword", payload.get("title"))
        self_status_id = payload.get("ucr_self_status_id")
        if isinstance(self_status_id, int) and data.cluster is not None:
            definition = data.cluster.status.get(str(self_status_id))
            payload["ucr_self_status_name"] = (
                definition.name if definition and definition.name else None
            )
        ucr_answered = payload.get("ucr_answered")
        if isinstance(ucr_answered, Mapping):
            payload["ucr_answered"] = _humanize_ucr_answered(data, ucr_answered)
        ucr_addressed = payload.get("ucr_addressed")
        if isinstance(ucr_addressed, Sequence) and not isinstance(ucr_addressed, str):
            payload["ucr_addressed"] = _humanize_ucr_user_list(data, ucr_addressed)
        ucr_adressed = payload.get("ucr_adressed")
        if isinstance(ucr_adressed, Sequence) and not isinstance(ucr_adressed, str):
            payload["ucr_adressed"] = _humanize_ucr_user_list(data, ucr_adressed)
        ucr_answeredcount = payload.get("ucr_answeredcount")
        if isinstance(ucr_answeredcount, Mapping):
            payload["ucr_answeredcount"] = _humanize_status_count_map(
                data,
                ucr_answeredcount,
            )
        ucr_read = payload.get("ucr_read")
        if isinstance(ucr_read, Sequence) and not isinstance(ucr_read, str):
            payload["ucr_read"] = _humanize_ucr_user_list(data, ucr_read)
        if payload.get("closed") is False:
            open_count += 1
        alarms_payload.append(payload)
    return {"alarms": alarms_payload, "open_count": open_count}


def _humanize_ucr_answered(
    data: PullData,
    answered: Mapping[str, object],
) -> Mapping[str, object]:
    """Resolve status/user IDs in ucr_answered to readable names."""
    resolved: dict[str, object] = {}
    for status_id_raw, entries in answered.items():
        status_name = _status_name_from_id(data, status_id_raw)
        if not isinstance(entries, Mapping):
            resolved[status_name] = entries
            continue

        resolved_entries: dict[str, object] = {}
        for user_id_raw, user_entry in entries.items():
            user_name = _user_name_from_id(data, user_id_raw)
            resolved_entries[user_name] = user_entry
        resolved[status_name] = resolved_entries
    return resolved


def _humanize_ucr_user_list(
    data: PullData,
    user_ids: Sequence[object],
) -> Sequence[str]:
    """Resolve user IDs in a list to readable names."""
    return [_user_name_from_id(data, user_id) for user_id in user_ids]


def _humanize_status_count_map(
    data: PullData,
    status_counts: Mapping[str, object],
) -> Mapping[str, object]:
    """Resolve status IDs in answered-count map to readable names."""
    resolved: dict[str, object] = {}
    for status_id_raw, count in status_counts.items():
        resolved[_status_name_from_id(data, status_id_raw)] = count
    return resolved


def _status_name_from_id(data: PullData, status_id: object) -> str:
    """Resolve a status ID to display name, fallback to ID string."""
    status_id_str = str(status_id)
    if data.cluster is None:
        return status_id_str
    definition = data.cluster.status.get(status_id_str)
    if definition is None or not definition.name:
        return status_id_str
    return definition.name


def _user_name_from_id(data: PullData, user_id: object) -> str:
    """Resolve a user/UCR ID to a display name, fallback to ID string."""
    user_id_str = str(user_id)

    if data.cluster is not None:
        consumer = data.cluster.consumer.get(user_id_str)
        if consumer is not None:
            name = " ".join(
                part for part in (consumer.firstname, consumer.lastname) if part
            ).strip()
            if name:
                return name
            if consumer.stdformat_name:
                return consumer.stdformat_name

    return user_id_str


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


def _cluster_attrs(data: PullData) -> Mapping[str, object]:
    """Return full cluster payload as attributes."""
    if data.cluster is None:
        return {}
    return data.cluster.model_dump(mode="json")


def _next_event_title(data: PullData) -> str | None:
    event = _next_event(data)
    return event.title if event else None


def _next_event_attrs(data: PullData) -> Mapping[str, str | int | None]:
    """Return attributes for the next event sensor."""
    event = _next_event(data)
    if event is None:
        return dict.fromkeys(EventResult.model_fields, None)
    return event.model_dump(mode="json")


def _status_counts(data: PullData) -> Mapping[int, int]:
    """Return aggregated user counts per status ID."""
    if data.monitor is not None:
        counts = _counts_from_monitor_anonymous(data.monitor)
        if counts:
            return counts

        counts = _counts_from_monitor_detailed(data.monitor)
        if counts:
            return counts

        counts = _counts_from_monitor_users(data.monitor)
        if counts:
            return counts

    return _counts_from_ucr(data)


def _counts_from_monitor_anonymous(monitor: object) -> Mapping[int, int]:
    """Build counts from monitor anonymous-by-status data."""
    anonymous_by_status = getattr(monitor, "anonymous_by_status", None)
    if not isinstance(anonymous_by_status, Mapping):
        return {}

    counts: dict[int, int] = {}
    for status_id_raw, entry in anonymous_by_status.items():
        if not str(status_id_raw).isdigit():
            continue
        all_count = getattr(entry, "all", None)
        if isinstance(all_count, int):
            counts[int(status_id_raw)] = all_count
    return counts


def _counts_from_monitor_detailed(monitor: object) -> Mapping[int, int]:
    """Build counts from monitor detailed-by-status data."""
    detailed_by_status = getattr(monitor, "detailed_by_status", None)
    if not isinstance(detailed_by_status, Mapping):
        return {}

    counts: dict[int, int] = {}
    for status_id_raw, entry in detailed_by_status.items():
        if not str(status_id_raw).isdigit():
            continue
        all_users = getattr(entry, "all", None)
        if isinstance(all_users, Sequence):
            counts[int(status_id_raw)] = len(all_users)
    return counts


def _counts_from_monitor_users(monitor: object) -> Mapping[int, int]:
    """Build counts from monitor user status entries."""
    users = getattr(monitor, "users", None)
    if not isinstance(users, Mapping):
        return {}

    counts: dict[int, int] = {}
    for user_entry in users.values():
        status_id = getattr(user_entry, "status", None)
        if not isinstance(status_id, int):
            continue
        counts[status_id] = counts.get(status_id, 0) + 1
    return counts


def _counts_from_ucr(data: PullData) -> Mapping[int, int]:
    """Build counts from UCR entries as fallback."""
    counts: dict[int, int] = {}
    for ucr in data.ucr.values():
        if ucr.status_id is None:
            continue
        counts[ucr.status_id] = counts.get(ucr.status_id, 0) + 1
    return counts


def _status_count_breakdown(data: PullData, status_id: int) -> Mapping[str, object]:
    """Return monitor breakdown details for a status count sensor."""
    if data.monitor is None:
        return {}
    anonymous_by_status = getattr(data.monitor, "anonymous_by_status", None)
    if not isinstance(anonymous_by_status, Mapping):
        return {}

    entry = anonymous_by_status.get(str(status_id))
    if entry is None:
        return {}

    qualification_raw = getattr(entry, "qualification", None)
    if not isinstance(qualification_raw, Mapping):
        return {}

    by_qualification_name: dict[str, int] = {}
    for qualification_id_raw, count in qualification_raw.items():
        if not isinstance(count, int):
            continue
        qualification_id = str(qualification_id_raw)
        qualification_name = qualification_id
        if data.cluster is not None:
            qualification = data.cluster.qualification.get(qualification_id)
            if (
                qualification is not None
                and qualification.shortname
                and qualification.shortname.strip()
            ):
                qualification_name = qualification.shortname
            elif qualification is not None and qualification.name:
                qualification_name = qualification.name
        by_qualification_name[qualification_name] = count

    return by_qualification_name


@dataclass(frozen=True, kw_only=True)
class Divera247SensorEntityDescription(SensorEntityDescription):
    """Describe a DIVERA sensor and how to derive its state from pull data."""

    value_fn: Callable[[PullData], object | None]
    attrs_fn: Callable[[PullData], Mapping[str, object]] | None = None


SENSORS: Sequence[Divera247SensorEntityDescription] = (
    Divera247SensorEntityDescription(
        key="status",
        translation_key="status",
        icon="mdi:account-alert",
        value_fn=_status_name,
        attrs_fn=_status_attrs,
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
        value_fn=_new_alarms,
    ),
    Divera247SensorEntityDescription(
        key="open_alarms",
        translation_key="open_alarms",
        icon="mdi:counter",
        value_fn=_open_alarms,
    ),
    Divera247SensorEntityDescription(
        key="all_alarms",
        translation_key="all_alarms",
        icon="mdi:format-list-bulleted",
        value_fn=_all_alarms_count,
        attrs_fn=_all_alarms_attrs,
    ),
    Divera247SensorEntityDescription(
        key="latest_alarm",
        translation_key="latest_alarm",
        icon="mdi:alarm-light-outline",
        value_fn=_latest_alarm_title,
        attrs_fn=_latest_alarm_attrs,
    ),
    Divera247SensorEntityDescription(
        key="new_messages",
        translation_key="new_messages",
        icon="mdi:message-badge",
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
        key="user",
        translation_key="user",
        icon="mdi:account",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_user_fullname,
    ),
    Divera247SensorEntityDescription(
        key="unit",
        translation_key="unit",
        icon="mdi:home-group",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_unit_name,
        attrs_fn=_cluster_attrs,
    ),
)


def _vehicle_payload(vehicle: VehicleStatusItem) -> Mapping[str, object]:
    """Return a dict payload for a vehicle model."""
    return vehicle.model_dump(mode="json")


def _vehicle_status_value(vehicle: VehicleStatusItem) -> int | str | None:
    """Pick a best-effort status value for a vehicle sensor."""
    return (
        vehicle.fmsstatus
        if vehicle.fmsstatus is not None
        else vehicle.fmsstatus_note
        if vehicle.fmsstatus_note is not None
        else vehicle.fmsstatus_id
    )


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: Divera247ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = entry.runtime_data.coordinator
    status_ids: list[int] = []
    if coordinator.data is not None and coordinator.data.cluster is not None:
        status_ids = sorted(
            int(status_id)
            for status_id in coordinator.data.cluster.status
            if str(status_id).isdigit()
        )
    async_add_entities(
        [
            *(Divera247Sensor(coordinator, description) for description in SENSORS),
            *(
                Divera247VehicleStatusSensor(coordinator, vehicle_id)
                for vehicle_id in coordinator.vehicle_status_by_id
            ),
            *(
                Divera247StatusCountSensor(coordinator, status_id)
                for status_id in status_ids
            ),
        ]
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
    def native_value(self) -> object | None:
        """Return the current value derived from the pull payload."""
        data = self.coordinator.data
        if data is None:
            return None
        return self.entity_description.value_fn(data)

    @property
    def extra_state_attributes(self) -> Mapping[str, object] | None:
        """Return any extra attributes declared on the description."""
        data = self.coordinator.data
        if data is None or self.entity_description.attrs_fn is None:
            return None
        attrs = dict(self.entity_description.attrs_fn(data))
        if self.entity_description.key == "latest_alarm":
            vehicle_ids = attrs.get("vehicle")
            if isinstance(vehicle_ids, Sequence) and not isinstance(vehicle_ids, str):
                resolved_vehicles: list[object] = []
                for vehicle_id in vehicle_ids:
                    key = str(vehicle_id)
                    vehicle = self.coordinator.vehicle_status_by_id.get(key)
                    if vehicle is None:
                        resolved_vehicles.append(vehicle_id)
                        continue
                    resolved_vehicles.append(
                        vehicle.name
                        or vehicle.shortname
                        or vehicle.fullname
                        or vehicle_id
                    )
                attrs["vehicle"] = resolved_vehicles
        return attrs


class Divera247VehicleStatusSensor(Divera247Entity, SensorEntity):
    """Sensor entity exposing status and metadata for one vehicle."""

    _attr_icon = "mdi:fire-truck"

    def __init__(
        self,
        coordinator: Divera247DataUpdateCoordinator,
        vehicle_id: str,
    ) -> None:
        """Initialise vehicle sensor entity."""
        super().__init__(
            coordinator,
            SensorEntityDescription(key=f"vehicle_{vehicle_id}_status"),
        )
        self._vehicle_id = vehicle_id

    @property
    def _vehicle(self) -> VehicleStatusItem | None:
        return self.coordinator.vehicle_status_by_id.get(self._vehicle_id)

    @property
    def name(self) -> str:
        """Return a human-readable entity name."""
        vehicle = self._vehicle
        if vehicle is None:
            return f"Vehicle {self._vehicle_id}"
        vehicle_name = vehicle.name or vehicle.shortname
        if vehicle_name:
            return vehicle_name
        return f"Vehicle {self._vehicle_id}"

    @property
    def native_value(self) -> int | str | None:
        """Return current vehicle status."""
        vehicle = self._vehicle
        if vehicle is None:
            return None
        return _vehicle_status_value(vehicle)

    @property
    def extra_state_attributes(self) -> Mapping[str, object]:
        """Return all available vehicle metadata as attributes."""
        vehicle = self._vehicle
        if vehicle is None:
            return {"vehicle_id": self._vehicle_id}
        payload = dict(_vehicle_payload(vehicle))
        payload.setdefault("vehicle_id", payload.get("id", self._vehicle_id))
        return payload


class Divera247StatusCountSensor(Divera247Entity, SensorEntity):
    """Sensor entity exposing the current count for one status ID."""

    _attr_icon = "mdi:counter"

    def __init__(
        self,
        coordinator: Divera247DataUpdateCoordinator,
        status_id: int,
    ) -> None:
        """Initialise status-count sensor entity."""
        super().__init__(
            coordinator,
            SensorEntityDescription(key=f"status_count_{status_id}"),
        )
        self._status_id = status_id

    @property
    def name(self) -> str:
        """Return a human-readable entity name."""
        cluster = self.coordinator.data.cluster if self.coordinator.data else None
        definition = (
            cluster.status.get(str(self._status_id))
            if cluster is not None and cluster.status
            else None
        )
        status_name = (
            definition.name if definition and definition.name else self._status_id
        )
        return f"Status: {status_name}"

    @property
    def native_value(self) -> int:
        """Return current number of users in this status."""
        data = self.coordinator.data
        if data is None:
            return 0
        return _status_counts(data).get(self._status_id, 0)

    @property
    def extra_state_attributes(self) -> Mapping[str, object]:
        """Return details for this status-count sensor."""
        cluster = self.coordinator.data.cluster if self.coordinator.data else None
        definition = (
            cluster.status.get(str(self._status_id))
            if cluster is not None and cluster.status
            else None
        )
        attrs: dict[str, object] = {
            "status_id": self._status_id,
            "status_name": definition.name if definition and definition.name else None,
        }
        data = self.coordinator.data
        if data is not None:
            attrs.update(_status_count_breakdown(data, self._status_id))
        return attrs
