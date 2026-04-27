"""Tests for status select platform."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.exceptions import HomeAssistantError

import custom_components.divera247.select as select_mod
from custom_components.divera247.api import Divera247ApiAuthError, Divera247ApiError
from custom_components.divera247.select import (
    Divera247StatusSelect,
    _visible_status_definitions,
)


def _definition(
    id_: int, name: str | None, hidden: bool = False, show: bool | None = True
) -> SimpleNamespace:
    return SimpleNamespace(id=id_, name=name, hidden=hidden, show_on_statusgeber=show)


def _coordinator(data: object | None) -> SimpleNamespace:
    if data is not None and not hasattr(data.cluster, "name"):
        data.cluster.name = "Cluster"
    return SimpleNamespace(
        data=data,
        config_entry=SimpleNamespace(
            entry_id="entry",
            title="title",
            runtime_data=SimpleNamespace(
                client=SimpleNamespace(async_set_status=AsyncMock())
            ),
        ),
        async_set_updated_data=Mock(),
        async_request_refresh=AsyncMock(),
    )


def test_visible_status_definitions_filters_and_order() -> None:
    """Expose only visible status definitions in deterministic order."""
    status = {
        "1": _definition(1, "A"),
        "2": _definition(2, "B", hidden=True),
        "3": _definition(3, None),
        "x": _definition(4, "X"),
        "4": _definition(4, "C", show=False),
    }
    data = SimpleNamespace(
        cluster=SimpleNamespace(
            status=status, statussorting_statusgeber=[1, 4, 2], statussorting=[2, 1]
        )
    )
    visible = _visible_status_definitions(data)
    assert [d.name for d in visible] == ["A"]
    assert _visible_status_definitions(SimpleNamespace(cluster=None)) == []
    data2 = SimpleNamespace(
        cluster=SimpleNamespace(
            status={"3": _definition(3, "C"), "2": _definition(2, None)},
            statussorting_statusgeber=None,
            statussorting=None,
        )
    )
    assert [d.id for d in _visible_status_definitions(data2)] == [3]


@pytest.mark.anyio
async def test_select_setup_entry_adds_entity() -> None:
    """Platform setup adds the status select entity."""
    defs = {"1": _definition(1, "A")}
    data = SimpleNamespace(
        cluster=SimpleNamespace(
            name="Cluster",
            status=defs,
            statussorting_statusgeber=[1],
            statussorting=[1],
        ),
        status=SimpleNamespace(status_id=1),
    )
    coordinator = _coordinator(data)
    add = Mock()
    await select_mod.async_setup_entry(
        SimpleNamespace(),
        SimpleNamespace(runtime_data=SimpleNamespace(coordinator=coordinator)),
        add,
    )
    assert add.call_count == 1


def test_select_options_and_current_option_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compute options/current option with pending state handling."""
    defs = {"1": _definition(1, "A"), "2": _definition(2, "B")}
    data = SimpleNamespace(
        cluster=SimpleNamespace(
            status=defs, statussorting_statusgeber=[1, 2], statussorting=[2, 1]
        ),
        status=SimpleNamespace(status_id=1),
    )
    coordinator = _coordinator(data)
    entity = Divera247StatusSelect(coordinator)
    assert entity.options == ["A", "B"]
    assert entity.current_option == "A"

    entity._pending_status_id = 2
    entity._pending_status_started_at = time.monotonic()
    assert entity.current_option == "B"
    data.status.status_id = 2
    assert entity.current_option == "B"
    assert entity._pending_status_id is None

    entity._pending_status_id = 1
    entity._pending_status_started_at = 0
    monkeypatch.setattr(select_mod.time, "monotonic", lambda: 9999.0)
    assert entity.current_option == "B"

    data.status.status_id = None
    assert entity.current_option is None
    data.status.status_id = 999
    assert entity.current_option is None

    none_entity = Divera247StatusSelect(_coordinator(None))
    assert none_entity.options == []
    assert none_entity.current_option is None


@pytest.mark.anyio
async def test_async_select_option_success_and_errors() -> None:
    """Select option calls API and maps error paths."""
    defs = {"1": _definition(1, "A"), "2": _definition(2, "B")}
    data = SimpleNamespace(
        cluster=SimpleNamespace(
            status=defs, statussorting_statusgeber=[1, 2], statussorting=[1, 2]
        ),
        status=SimpleNamespace(status_id=1),
    )
    coordinator = _coordinator(data)
    entity = Divera247StatusSelect(coordinator)
    await entity.async_select_option("B")
    coordinator.config_entry.runtime_data.client.async_set_status.assert_awaited()
    coordinator.async_request_refresh.assert_awaited()
    assert data.status.status_id == 2

    coordinator.config_entry.runtime_data.client.async_set_status = AsyncMock(
        side_effect=Divera247ApiAuthError("auth")
    )
    with pytest.raises(HomeAssistantError, match="auth failed"):
        await entity.async_select_option("B")

    coordinator.config_entry.runtime_data.client.async_set_status = AsyncMock(
        side_effect=Divera247ApiError("api")
    )
    with pytest.raises(HomeAssistantError, match="API error"):
        await entity.async_select_option("B")

    with pytest.raises(HomeAssistantError, match="Unknown DIVERA status option"):
        await entity.async_select_option("missing")
