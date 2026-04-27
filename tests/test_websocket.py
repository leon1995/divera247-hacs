"""Tests for websocket listener."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import custom_components.divera247.websocket as ws_mod


class UserStatusEvent:
    """Minimal stand-in for user-status websocket events."""

    def __init__(self, status: object, type_: str = "user-status") -> None:
        """Store event type and status payload."""
        self.status = status
        self.type = type_


class ClusterVehicleEvent:
    """Minimal stand-in for cluster-vehicle websocket events."""

    def __init__(self, type_: str = "cluster-vehicle") -> None:
        """Store event type."""
        self.type = type_


class ClusterPullEvent:
    """Minimal stand-in for cluster-pull websocket events."""

    def __init__(self, type_: str = "cluster-pull") -> None:
        """Store event type."""
        self.type = type_


class ClusterMonitorEvent:
    """Minimal stand-in for cluster-monitor websocket events."""

    def __init__(self, type_: str = "cluster-monitor") -> None:
        """Store event type."""
        self.type = type_


class UnknownEvent:
    """Minimal stand-in for unknown websocket events."""

    def __init__(self, type_: str = "unknown") -> None:
        """Store event type."""
        self.type = type_


def _listener() -> ws_mod.Divera247WebSocketListener:
    def _create_bg(coro: object, name: str) -> SimpleNamespace:  # noqa: ARG001
        coro.close()
        return SimpleNamespace(done=lambda: False)

    def _create_task(coro: object) -> None:
        coro.close()

    hass = SimpleNamespace(
        async_create_background_task=Mock(side_effect=_create_bg),
        async_create_task=Mock(side_effect=_create_task),
    )
    coordinator = SimpleNamespace(
        data=SimpleNamespace(status="old"),
        async_request_refresh=AsyncMock(),
        async_set_updated_data=Mock(),
        async_update_listeners=Mock(),
        vehicle_status_by_id={},
    )
    api_client = SimpleNamespace(
        raw_client=object(), async_get_vehicle_status=AsyncMock()
    )
    return ws_mod.Divera247WebSocketListener(hass, coordinator, api_client, 1)


def test_start_stop_dispatch_apply_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dispatch known/fallback events and patch user status."""
    monkeypatch.setattr(ws_mod, "UserStatusEvent", UserStatusEvent)
    monkeypatch.setattr(ws_mod, "ClusterVehicleEvent", ClusterVehicleEvent)
    monkeypatch.setattr(ws_mod, "ClusterPullEvent", ClusterPullEvent)
    monkeypatch.setattr(ws_mod, "ClusterMonitorEvent", ClusterMonitorEvent)
    l = _listener()
    l.async_start()
    l.async_start()
    l._dispatch(UserStatusEvent("new"))
    assert l._coordinator.data.status == "new"
    l._dispatch(ClusterVehicleEvent())
    l._dispatch(ClusterPullEvent())
    l._dispatch(ClusterMonitorEvent())
    l._dispatch(UnknownEvent("cluster-vehicle"))
    l._dispatch(UnknownEvent("cluster-pull"))
    l._dispatch(UnknownEvent("other"))


@pytest.mark.anyio
async def test_stop_and_refresh_vehicle_status_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stop task and cover vehicle refresh success/fallback branches."""
    l = _listener()
    task = asyncio.create_task(asyncio.sleep(1))
    l._task = task
    await l.async_stop()
    assert l._task is None
    await l.async_stop()

    l._api_client.async_get_vehicle_status = AsyncMock(
        return_value=SimpleNamespace(
            success=True, data=[SimpleNamespace(id=1), SimpleNamespace(id=None)]
        )
    )
    await l._async_refresh_vehicle_status()
    assert l._coordinator.vehicle_status_by_id == {
        "1": l._coordinator.vehicle_status_by_id["1"]
    }

    l._api_client.async_get_vehicle_status = AsyncMock(
        side_effect=ws_mod.Divera247ApiError("x")
    )
    await l._async_refresh_vehicle_status()

    l._api_client.async_get_vehicle_status = AsyncMock(
        return_value=SimpleNamespace(success=False, data=[])
    )
    await l._async_refresh_vehicle_status()


@pytest.mark.anyio
async def test_run_exception_paths_and_shutdown_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover run-loop exception handling and shutdown-group detection."""
    l = _listener()

    async def gen_ok():
        yield UnknownEvent("other")

    monkeypatch.setattr(ws_mod, "stream_websocket", lambda *_args, **_kwargs: gen_ok())
    await l._run()

    async def gen_cancel():
        raise asyncio.CancelledError()
        yield

    monkeypatch.setattr(
        ws_mod, "stream_websocket", lambda *_args, **_kwargs: gen_cancel()
    )
    with pytest.raises(asyncio.CancelledError):
        await l._run()

    class AuthErr(Exception):
        pass

    monkeypatch.setattr(ws_mod, "WebSocketAuthenticationError", AuthErr)

    async def gen_auth():
        raise AuthErr("x")
        yield

    monkeypatch.setattr(
        ws_mod, "stream_websocket", lambda *_args, **_kwargs: gen_auth()
    )
    await l._run()

    shutdown_group = ExceptionGroup(
        "g",
        [
            RuntimeError("cancel scope"),
            ExceptionGroup("n", [RuntimeError("cancel scope")]),
        ],
    )

    async def gen_shutdown():
        raise shutdown_group
        yield

    monkeypatch.setattr(
        ws_mod, "stream_websocket", lambda *_args, **_kwargs: gen_shutdown()
    )
    await l._run()

    async def gen_crash():
        raise ValueError("boom")
        yield

    monkeypatch.setattr(
        ws_mod, "stream_websocket", lambda *_args, **_kwargs: gen_crash()
    )
    await l._run()

    assert (
        ws_mod.Divera247WebSocketListener._is_shutdown_exception_group(shutdown_group)
        is True
    )
    assert (
        ws_mod.Divera247WebSocketListener._is_shutdown_exception_group(ValueError("x"))
        is False
    )
    assert (
        ws_mod.Divera247WebSocketListener._is_shutdown_exception_group(
            ExceptionGroup("x", [ValueError("y")])
        )
        is False
    )
    assert (
        ws_mod.Divera247WebSocketListener._is_shutdown_exception_group(
            ExceptionGroup("x", [RuntimeError("other")])
        )
        is False
    )
    recursive_bad = ExceptionGroup(
        "outer",
        [ExceptionGroup("inner", [RuntimeError("different message")])],
    )
    assert (
        ws_mod.Divera247WebSocketListener._is_shutdown_exception_group(recursive_bad)
        is False
    )


def test_apply_user_status_without_data_schedules_refresh() -> None:
    """Schedule a refresh when status event arrives without cached data."""
    l = _listener()
    l._coordinator.data = None
    l._apply_user_status(UserStatusEvent("new"))
    assert l._hass.async_create_task.call_count == 1
