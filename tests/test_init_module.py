"""Tests for integration init module."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.exceptions import HomeAssistantError

import custom_components.divera247.__init__ as init_mod
from custom_components.divera247.const import (
    ATTR_NOTE,
    ATTR_STATUS_ID,
    ATTR_VEHICLE_ID,
    CONF_ACCESS_KEY,
    DOMAIN,
)


@pytest.mark.anyio
async def test_setup_and_unload_and_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up runtime, unload resources, and reload entry."""
    client = SimpleNamespace(async_close=AsyncMock())
    coordinator = SimpleNamespace(
        vehicle_status_by_id={},
        data=SimpleNamespace(
            cluster=SimpleNamespace(name="Muster"), ucr_active=1, ucr_default=None
        ),
        async_config_entry_first_refresh=AsyncMock(),
    )
    listener = SimpleNamespace(async_start=Mock(), async_stop=AsyncMock())
    monkeypatch.setattr(init_mod, "Divera247ApiClient", lambda _k: client)
    monkeypatch.setattr(
        init_mod, "Divera247DataUpdateCoordinator", lambda **_k: coordinator
    )
    monkeypatch.setattr(
        init_mod, "async_get_loaded_integration", lambda _h, _d: "integration"
    )
    monkeypatch.setattr(init_mod, "Divera247WebSocketListener", lambda **_k: listener)

    hass = SimpleNamespace(
        async_add_executor_job=AsyncMock(side_effect=lambda fn, key: fn(key)),
        config_entries=SimpleNamespace(
            async_forward_entry_setups=AsyncMock(),
            async_unload_platforms=AsyncMock(return_value=True),
            async_reload=AsyncMock(),
            async_update_entry=Mock(),
            async_entries=lambda _d: [],
        ),
        services=SimpleNamespace(has_service=lambda d, s: False, async_register=Mock()),
    )
    entry = SimpleNamespace(
        data={CONF_ACCESS_KEY: "k"},
        domain=DOMAIN,
        entry_id="entry",
        title="old",
        runtime_data=None,
        async_on_unload=Mock(),
        add_update_listener=lambda cb: cb,
    )
    assert await init_mod.async_setup_entry(hass, entry) is True
    assert entry.runtime_data.ws_listener is listener

    assert await init_mod.async_unload_entry(hass, entry) is True
    listener.async_stop.assert_awaited_once()
    client.async_close.assert_awaited_once()

    await init_mod.async_reload_entry(hass, entry)
    hass.config_entries.async_reload.assert_awaited_once_with("entry")


def test_update_entry_title_paths() -> None:
    """Update title based on cluster/UCR naming rules."""
    hass = SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=Mock()))
    entry = SimpleNamespace(title="old")
    init_mod._async_update_entry_title(hass, entry, None)
    data = SimpleNamespace(
        cluster=SimpleNamespace(name="Muster"), ucr_active=2, ucr_default=None
    )
    init_mod._async_update_entry_title(hass, entry, data)
    hass.config_entries.async_update_entry.assert_called_once()
    entry2 = SimpleNamespace(title="Feuerwehr Muster 2")
    init_mod._async_update_entry_title(hass, entry2, data)
    data2 = SimpleNamespace(
        cluster=SimpleNamespace(name=" Feuerwehr X "), ucr_active=None, ucr_default=None
    )
    init_mod._async_update_entry_title(hass, entry2, data2)


@pytest.mark.anyio
async def test_register_services_and_handler_paths() -> None:
    """Register service and cover all handler branches."""
    registered: dict[str, object] = {}

    def register(_domain: str, _service: str, handler: object, schema: object) -> None:
        registered["handler"] = handler
        registered["schema"] = schema

    hass = SimpleNamespace(
        services=SimpleNamespace(
            has_service=lambda d, s: False, async_register=register
        ),
        config_entries=SimpleNamespace(async_entries=lambda _d: []),
    )
    init_mod._async_register_services(hass)
    handler = registered["handler"]

    with pytest.raises(HomeAssistantError, match="No loaded DIVERA"):
        await handler(SimpleNamespace(data={ATTR_STATUS_ID: 1}))

    runtime = SimpleNamespace(
        client=SimpleNamespace(async_set_status=AsyncMock()),
        coordinator=SimpleNamespace(async_request_refresh=AsyncMock()),
    )
    entry = SimpleNamespace(runtime_data=runtime)
    hass.config_entries = SimpleNamespace(async_entries=lambda _d: [entry])
    await handler(
        SimpleNamespace(data={ATTR_STATUS_ID: 5, ATTR_NOTE: "n", ATTR_VEHICLE_ID: 7})
    )
    runtime.client.async_set_status.assert_awaited_once()
    runtime.coordinator.async_request_refresh.assert_awaited_once()

    runtime.client.async_set_status = AsyncMock(
        side_effect=init_mod.Divera247ApiAuthError("x")
    )
    with pytest.raises(HomeAssistantError, match="auth failed"):
        await handler(SimpleNamespace(data={ATTR_STATUS_ID: 1}))

    runtime.client.async_set_status = AsyncMock(
        side_effect=init_mod.Divera247ApiError("x")
    )
    with pytest.raises(HomeAssistantError, match="API error"):
        await handler(SimpleNamespace(data={ATTR_STATUS_ID: 1}))

    hass2 = SimpleNamespace(
        services=SimpleNamespace(has_service=lambda d, s: True, async_register=Mock()),
        config_entries=SimpleNamespace(async_entries=lambda _d: []),
    )
    init_mod._async_register_services(hass2)
