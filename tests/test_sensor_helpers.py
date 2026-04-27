"""Tests for helper functions and entities in the sensor platform."""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from custom_components.divera247.sensor import (
    Divera247Sensor,
    Divera247SensorEntityDescription,
    Divera247StatusCountSensor,
    Divera247VehicleStatusSensor,
    _all_alarm_items,
    _all_alarms_attrs,
    _all_alarms_count,
    _cluster_attrs,
    _counts_from_monitor_anonymous,
    _counts_from_monitor_detailed,
    _counts_from_monitor_users,
    _counts_from_ucr,
    _humanize_ucr_answered,
    _items_sorted,
    _latest_alarm,
    _latest_alarm_attrs,
    _latest_alarm_title,
    _new_alarms,
    _new_messages,
    _next_event,
    _next_event_attrs,
    _next_event_title,
    _next_status_reset,
    _open_alarms,
    _status_attrs,
    _status_count_breakdown,
    _status_counts,
    _status_name,
    _status_name_from_id,
    _status_set_date,
    _timestamp,
    _unit_name,
    _user_fullname,
    _user_name_from_id,
    _vehicle_payload,
    _vehicle_status_value,
    async_setup_entry,
)


class FakeModel:
    """Tiny helper that mimics pydantic model_dump."""

    def __init__(self, **values: object) -> None:
        """Store arbitrary fields for test payload creation."""
        self.__dict__.update(values)

    def model_dump(self, mode: str = "json") -> dict[str, object]:  # noqa: ARG002
        """Return object fields in dict form."""
        return dict(self.__dict__)


def _build_data() -> SimpleNamespace:
    now = datetime.datetime.now(tz=datetime.UTC)
    status_def = {
        "42": SimpleNamespace(name="Einsatzbereit"),
        "43": SimpleNamespace(name="Nicht"),
    }
    cluster = FakeModel(
        name="Feuerwehr Muster",
        status=status_def,
        consumer={
            "5": SimpleNamespace(
                firstname="Max",
                lastname="Mustermann",
                stdformat_name="M. Mustermann",
            )
        },
        qualification={"10": SimpleNamespace(shortname="PA", name="Atemschutz")},
    )
    alarm_1 = FakeModel(
        id=10,
        title="B2",
        closed=False,
        vehicle=[1, 2],
        ucr_self_status_id=42,
        ucr_answered={"42": {"5": {"time": 1}}},
        ucr_addressed=[5],
        ucr_adressed=[5],
        ucr_answeredcount={"42": 2},
        ucr_read=[5],
    )
    alarm_2 = FakeModel(id=11, title="BMA", closed=True, vehicle=[3])
    event_old = FakeModel(
        title="Vergangen",
        start=now - datetime.timedelta(hours=3),
        end=now - datetime.timedelta(hours=2),
    )
    event_new = FakeModel(
        title="Uebung",
        start=now + datetime.timedelta(hours=2),
        end=now + datetime.timedelta(hours=3),
    )
    return SimpleNamespace(
        status=FakeModel(
            status_id=42,
            note="note",
            vehicle_id=9,
            status_set_date=1700000000,
            status_reset_date="1700001000",
        ),
        cluster=cluster,
        alarm=SimpleNamespace(
            new=3, items={"10": alarm_1, "11": alarm_2}, sorting=[10, 11]
        ),
        news=SimpleNamespace(new=7),
        events=SimpleNamespace(items={"1": event_old, "2": event_new}),
        user=SimpleNamespace(firstname="Jane", lastname="Doe"),
        monitor=SimpleNamespace(
            anonymous_by_status={"42": SimpleNamespace(all=4, qualification={"10": 4})},
            detailed_by_status={"43": SimpleNamespace(all=[1, 2])},
            users={"1": SimpleNamespace(status=42), "2": SimpleNamespace(status=42)},
        ),
        ucr={"1": SimpleNamespace(status_id=43), "2": SimpleNamespace(status_id=None)},
    )


def _build_coordinator(data: object | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        data=data,
        vehicle_status_by_id={
            "1": FakeModel(
                id=1,
                name="HLF",
                shortname="H1",
                fullname="HLF 20",
                fmsstatus=None,
                fmsstatus_note=None,
                fmsstatus_id=None,
            ),
            "2": FakeModel(
                id=2,
                name=None,
                shortname="DLK",
                fullname="Drehleiter",
                fmsstatus=None,
                fmsstatus_note=None,
                fmsstatus_id=None,
            ),
        },
        config_entry=SimpleNamespace(entry_id="entry-1", title="FW", runtime_data=None),
    )


def test_timestamp_handles_none_datetime_and_numeric_string() -> None:
    """Timestamp helper normalizes supported input variants."""
    aware = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    naive = datetime.datetime(2026, 1, 2)

    assert _timestamp(None) is None
    assert _timestamp(aware) is aware
    assert _timestamp(naive) == naive.replace(tzinfo=datetime.UTC)
    assert _timestamp("1700000000") == datetime.datetime.fromtimestamp(
        1700000000,
        tz=datetime.UTC,
    )
    assert _timestamp("not-a-ts") is None


def test_status_name_from_id_uses_cluster_name_fallbacks_to_id() -> None:
    """Status names resolve from cluster definitions if available."""
    cluster = SimpleNamespace(status={"42": SimpleNamespace(name="Einsatzbereit")})
    data = SimpleNamespace(cluster=cluster)

    assert _status_name_from_id(data, 42) == "Einsatzbereit"
    assert _status_name_from_id(data, 99) == "99"


def test_user_name_from_id_prefers_consumer_fullname() -> None:
    """User IDs resolve to readable names from cluster consumer data."""
    consumer = SimpleNamespace(
        firstname="Max",
        lastname="Mustermann",
        stdformat_name="M. Mustermann",
    )
    cluster = SimpleNamespace(consumer={"5": consumer})
    data = SimpleNamespace(cluster=cluster)

    assert _user_name_from_id(data, 5) == "Max Mustermann"
    assert _user_name_from_id(data, 7) == "7"


def test_status_counts_prefers_monitor_anonymous_data() -> None:
    """Monitor anonymous-by-status data has highest priority for counts."""
    monitor = SimpleNamespace(
        anonymous_by_status={
            "1": SimpleNamespace(all=4),
            "2": SimpleNamespace(all=2),
            "x": SimpleNamespace(all=9),
        },
        detailed_by_status={},
        users={},
    )
    data = SimpleNamespace(monitor=monitor, ucr={})

    assert _status_counts(data) == {1: 4, 2: 2}


def test_status_counts_falls_back_to_ucr_data() -> None:
    """UCR map is used when no monitor data can be consumed."""
    data = SimpleNamespace(
        monitor=None,
        ucr={
            "1": SimpleNamespace(status_id=1),
            "2": SimpleNamespace(status_id=2),
            "3": SimpleNamespace(status_id=1),
            "4": SimpleNamespace(status_id=None),
        },
    )

    assert _counts_from_ucr(data) == {1: 2, 2: 1}
    assert _status_counts(data) == {1: 2, 2: 1}


def test_status_count_breakdown_resolves_qualification_names() -> None:
    """Qualification IDs are translated to cluster short names where possible."""
    monitor = SimpleNamespace(
        anonymous_by_status={
            "3": SimpleNamespace(
                qualification={
                    "10": 3,
                    "11": 1,
                    "99": 2,
                }
            )
        }
    )
    cluster = SimpleNamespace(
        qualification={
            "10": SimpleNamespace(shortname="PA", name="Atemschutz"),
            "11": SimpleNamespace(shortname=None, name="Maschinist"),
        }
    )
    data = SimpleNamespace(monitor=monitor, cluster=cluster)

    assert _status_count_breakdown(data, 3) == {"PA": 3, "Maschinist": 1, "99": 2}


def test_status_and_unit_helpers() -> None:
    """Cover status, unit, timestamp, and metadata helper functions."""
    data = _build_data()
    assert _status_name(data) == "Einsatzbereit"
    assert _status_attrs(data)["status_id"] == 42
    assert _status_set_date(data) == datetime.datetime.fromtimestamp(
        1700000000, tz=datetime.UTC
    )
    assert _next_status_reset(data) == datetime.datetime.fromtimestamp(
        1700001000, tz=datetime.UTC
    )
    data.status.status_reset_date = 1700002000
    assert _next_status_reset(data) == datetime.datetime.fromtimestamp(
        1700002000, tz=datetime.UTC
    )
    data.status.status_reset_date = "n/a"
    assert _next_status_reset(data) is None
    assert _unit_name(data) == "Feuerwehr Muster"
    assert _cluster_attrs(data)["name"] == "Feuerwehr Muster"
    assert _user_fullname(data) == "Jane Doe"
    assert _new_alarms(data) == 3
    assert _new_messages(data) == 7


def test_alarm_helpers_resolve_and_humanize() -> None:
    """Cover latest/all alarm extraction and humanization paths."""
    data = _build_data()
    latest = _latest_alarm(data)
    assert latest is not None
    assert _latest_alarm_title(data) == "B2"
    attrs = _latest_alarm_attrs(data)
    assert attrs["ucr_self_status_name"] == "Einsatzbereit"
    assert attrs["ucr_addressed"] == ["Max Mustermann"]
    assert attrs["ucr_answeredcount"] == {"Einsatzbereit": 2}
    all_attrs = _all_alarms_attrs(data)
    assert all_attrs["open_count"] == 1
    assert len(all_attrs["alarms"]) == 2
    assert len(_all_alarm_items(data)) == 2
    assert _all_alarms_count(data) == 2
    assert _open_alarms(data) == 1


def test_event_helpers_select_next_future_event() -> None:
    """Select the nearest upcoming event from mixed event data."""
    data = _build_data()
    event = _next_event(data)
    assert event is not None
    assert _next_event_title(data) == "Uebung"
    attrs = _next_event_attrs(data)
    assert attrs["title"] == "Uebung"


def test_event_helpers_without_event_return_none_payload() -> None:
    """Return empty event payload when no future event is available."""
    data = SimpleNamespace(events=None)
    assert _next_event(data) is None
    assert _next_event_title(data) is None
    attrs = _next_event_attrs(data)
    assert "title" in attrs
    assert attrs["title"] is None

    now = datetime.datetime.now(tz=datetime.UTC)
    past = FakeModel(
        title="past",
        start=now - datetime.timedelta(hours=2),
        end=now - datetime.timedelta(hours=1),
    )
    only_past_data = SimpleNamespace(events=SimpleNamespace(items={"1": past}))
    assert _next_event(only_past_data) is None


def test_monitor_count_helper_variants() -> None:
    """Count helpers parse anonymous, detailed, and user maps."""
    anonymous = SimpleNamespace(
        anonymous_by_status={"1": SimpleNamespace(all=3), "x": SimpleNamespace(all=9)}
    )
    assert _counts_from_monitor_anonymous(anonymous) == {1: 3}
    detailed = SimpleNamespace(
        detailed_by_status={
            "2": SimpleNamespace(all=[1, 2, 3]),
            "x": SimpleNamespace(all=[1]),
        }
    )
    assert _counts_from_monitor_detailed(detailed) == {2: 3}
    users = SimpleNamespace(
        users={
            "1": SimpleNamespace(status=5),
            "2": SimpleNamespace(status=5),
            "3": SimpleNamespace(status="x"),
        }
    )
    assert _counts_from_monitor_users(users) == {5: 2}
    assert _counts_from_monitor_anonymous(SimpleNamespace(anonymous_by_status=[])) == {}
    assert _counts_from_monitor_detailed(SimpleNamespace(detailed_by_status=[])) == {}
    assert _counts_from_monitor_users(SimpleNamespace(users=[])) == {}


def test_vehicle_helpers() -> None:
    """Vehicle helper functions return expected payload and value."""
    vehicle = FakeModel(id=1, fmsstatus=2, fmsstatus_note="note", fmsstatus_id=9)
    assert _vehicle_payload(vehicle)["id"] == 1
    assert _vehicle_status_value(vehicle) == 2
    vehicle2 = FakeModel(id=2, fmsstatus=None, fmsstatus_note="abc", fmsstatus_id=9)
    assert _vehicle_status_value(vehicle2) == "abc"
    vehicle3 = FakeModel(id=3, fmsstatus=None, fmsstatus_note=None, fmsstatus_id=4)
    assert _vehicle_status_value(vehicle3) == 4


def test_divera_sensor_entity_properties() -> None:
    """Generic sensor entity resolves value and transformed attributes."""
    data = _build_data()
    coordinator = _build_coordinator(data)
    description = Divera247SensorEntityDescription(
        key="latest_alarm",
        value_fn=_latest_alarm_title,
        attrs_fn=_latest_alarm_attrs,
    )
    entity = Divera247Sensor(coordinator, description)
    assert entity.native_value == "B2"
    attrs = entity.extra_state_attributes
    assert attrs is not None
    assert attrs["vehicle"] == ["HLF", "DLK"]
    data.alarm.items["10"].vehicle = [99]
    attrs = entity.extra_state_attributes
    assert attrs is not None
    assert attrs["vehicle"] == [99]
    coordinator.data = None
    assert entity.native_value is None
    assert entity.extra_state_attributes is None


def test_vehicle_sensor_entity_properties() -> None:
    """Vehicle sensor exposes fallback names and state attributes."""
    coordinator = _build_coordinator(_build_data())
    entity = Divera247VehicleStatusSensor(coordinator, "1")
    assert entity.name == "HLF"
    assert entity.native_value is None  # fms fields not set in fake payload
    assert entity.extra_state_attributes["vehicle_id"] == 1

    entity_missing = Divera247VehicleStatusSensor(coordinator, "999")
    assert entity_missing.name == "Vehicle 999"
    assert entity_missing.native_value is None
    assert entity_missing.extra_state_attributes == {"vehicle_id": "999"}


def test_status_count_sensor_properties() -> None:
    """Status count entity reports current count and breakdown attrs."""
    data = _build_data()
    coordinator = _build_coordinator(data)
    entity = Divera247StatusCountSensor(coordinator, 42)
    assert entity.name == "Status: Einsatzbereit"
    assert entity.native_value == 4
    attrs = entity.extra_state_attributes
    assert attrs["status_id"] == 42
    assert attrs["PA"] == 4
    coordinator.data = None
    assert entity.native_value == 0


@pytest.mark.anyio
async def test_async_setup_entry_adds_all_dynamic_entities() -> None:
    """Sensor setup creates base, vehicle, and status count entities."""
    data = _build_data()
    coordinator = _build_coordinator(data)
    entry = SimpleNamespace(runtime_data=SimpleNamespace(coordinator=coordinator))
    add_entities = Mock()

    await async_setup_entry(SimpleNamespace(), entry, add_entities)

    assert add_entities.call_count == 1
    entities = list(add_entities.call_args.args[0])
    assert any(isinstance(entity, Divera247VehicleStatusSensor) for entity in entities)
    assert any(isinstance(entity, Divera247StatusCountSensor) for entity in entities)


def test_helper_edge_cases_return_safe_defaults() -> None:
    """Helper functions return safe defaults for missing payload blocks."""
    empty = SimpleNamespace(
        status=None,
        cluster=None,
        alarm=None,
        news=None,
        events=SimpleNamespace(items={}),
        user=None,
        monitor=SimpleNamespace(
            anonymous_by_status=None, detailed_by_status=None, users=None
        ),
        ucr={},
    )
    assert _timestamp(" ") is None
    assert _status_name(empty) is None
    assert _status_attrs(empty) == {"status_id": None, "note": None, "vehicle_id": None}
    assert _status_set_date(empty) is None
    assert _next_status_reset(empty) is None
    assert _new_alarms(empty) is None
    assert _new_messages(empty) is None
    assert _latest_alarm(empty) is None
    assert _all_alarm_items(empty) == []
    assert _open_alarms(empty) == 0
    assert _latest_alarm_attrs(empty) == {}
    assert _latest_alarm_title(empty) is None
    assert _next_event(empty) is None
    assert _next_event_title(empty) is None
    assert _user_fullname(empty) is None
    assert _unit_name(empty) is None
    assert _cluster_attrs(empty) == {}
    assert _status_name_from_id(empty, 1) == "1"
    assert _status_count_breakdown(empty, 1) == {}


def test_helper_branch_fallbacks_for_monitor_and_names() -> None:
    """Monitor fallback branches and name resolution work as expected."""
    monitor_detailed = SimpleNamespace(
        anonymous_by_status={},
        detailed_by_status={"2": SimpleNamespace(all=[1, 2, 3])},
        users={},
    )
    data = SimpleNamespace(monitor=monitor_detailed, ucr={})
    assert _status_counts(data) == {2: 3}

    monitor_users = SimpleNamespace(
        anonymous_by_status={},
        detailed_by_status={},
        users={"1": SimpleNamespace(status=7), "2": SimpleNamespace(status=7)},
    )
    data2 = SimpleNamespace(monitor=monitor_users, ucr={})
    assert _status_counts(data2) == {7: 2}

    cluster = SimpleNamespace(
        consumer={
            "8": SimpleNamespace(
                firstname=None, lastname=None, stdformat_name="Display Name"
            )
        }
    )
    assert _user_name_from_id(SimpleNamespace(cluster=cluster), 8) == "Display Name"

    assert _items_sorted({"1": "a"}, None) == ["a"]
    assert _items_sorted({}, [1]) == []


def test_status_count_breakdown_early_returns_and_count_filter() -> None:
    """Breakdown helper returns empty maps on invalid monitor structures."""
    assert _status_count_breakdown(SimpleNamespace(monitor=None), 1) == {}

    data_no_entry = SimpleNamespace(
        monitor=SimpleNamespace(anonymous_by_status={}),
        cluster=None,
    )
    assert _status_count_breakdown(data_no_entry, 3) == {}

    data_no_map = SimpleNamespace(
        monitor=SimpleNamespace(
            anonymous_by_status={"3": SimpleNamespace(qualification=None)}
        ),
        cluster=None,
    )
    assert _status_count_breakdown(data_no_map, 3) == {}

    data_non_int = SimpleNamespace(
        monitor=SimpleNamespace(
            anonymous_by_status={
                "3": SimpleNamespace(qualification={"x": "bad", "5": 2})
            }
        ),
        cluster=None,
    )
    assert _status_count_breakdown(data_non_int, 3) == {"5": 2}


def test_humanize_answered_keeps_non_mapping_payload() -> None:
    """Humanization keeps non-mapping values unchanged."""
    data = _build_data()
    resolved = _humanize_ucr_answered(data, {"42": 1})
    assert resolved == {"Einsatzbereit": 1}


def test_vehicle_sensor_fallback_names_and_attributes() -> None:
    """Vehicle sensor falls back to generic names when needed."""
    coordinator = _build_coordinator(_build_data())
    coordinator.vehicle_status_by_id["1"] = FakeModel(
        id=1,
        name=None,
        shortname=None,
        fullname="Only Full",
        fmsstatus=None,
        fmsstatus_note=None,
        fmsstatus_id=5,
    )
    vehicle = Divera247VehicleStatusSensor(coordinator, "1")
    assert vehicle.name == "Vehicle 1"
    assert vehicle.native_value == 5

    coordinator.vehicle_status_by_id["2"] = FakeModel(
        id=2,
        name="Named",
        shortname=None,
        fullname=None,
        fmsstatus=1,
        fmsstatus_note=None,
        fmsstatus_id=None,
    )
    vehicle2 = Divera247VehicleStatusSensor(coordinator, "2")
    assert vehicle2.name == "Named"
    assert vehicle2.extra_state_attributes["vehicle_id"] == 2
