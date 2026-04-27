"""Tests for config flow."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import custom_components.divera247.config_flow as cf_mod
from custom_components.divera247.const import CONF_ACCESS_KEY


@pytest.mark.anyio
async def test_step_user_shows_form_and_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Show form and create entry on valid credentials."""
    flow = cf_mod.Divera247ConfigFlow()
    flow.hass = SimpleNamespace()
    flow.async_show_form = lambda **kwargs: {"type": "form", **kwargs}
    flow.async_create_entry = lambda **kwargs: {"type": "create_entry", **kwargs}
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = lambda: None
    monkeypatch.setattr(flow, "_test_access_key", AsyncMock(return_value="FW 1"))

    form = await flow.async_step_user(None)
    assert form["type"] == "form"

    result = await flow.async_step_user({CONF_ACCESS_KEY: "  key  "})
    assert result["type"] == "create_entry"
    assert result["title"] == "FW 1"
    assert result["data"][CONF_ACCESS_KEY] == "key"


@pytest.mark.anyio
async def test_step_user_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """Map API exceptions to expected config-flow errors."""
    flow = cf_mod.Divera247ConfigFlow()
    flow.hass = SimpleNamespace()
    flow.async_show_form = lambda **kwargs: kwargs
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = lambda: None
    flow.async_create_entry = lambda **kwargs: kwargs

    monkeypatch.setattr(
        flow,
        "_test_access_key",
        AsyncMock(side_effect=cf_mod.Divera247ApiAuthError("x")),
    )
    res = await flow.async_step_user({CONF_ACCESS_KEY: "k"})
    assert res["errors"]["base"] == "invalid_auth"

    monkeypatch.setattr(
        flow,
        "_test_access_key",
        AsyncMock(side_effect=cf_mod.Divera247ApiCommunicationError("x")),
    )
    res = await flow.async_step_user({CONF_ACCESS_KEY: "k"})
    assert res["errors"]["base"] == "cannot_connect"

    monkeypatch.setattr(
        flow, "_test_access_key", AsyncMock(side_effect=cf_mod.Divera247ApiError("x"))
    )
    res = await flow.async_step_user({CONF_ACCESS_KEY: "k"})
    assert res["errors"]["base"] == "unknown"


@pytest.mark.anyio
async def test_test_access_key_success_and_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validate access key and derive title from pull data."""
    flow = cf_mod.Divera247ConfigFlow()
    client = SimpleNamespace(
        async_get_pull_all=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                data=SimpleNamespace(
                    cluster=SimpleNamespace(name="Muster"),
                    ucr_active=7,
                    ucr_default=None,
                ),
            )
        ),
        async_close=AsyncMock(),
    )
    flow.hass = SimpleNamespace(async_add_executor_job=AsyncMock(return_value=client))
    monkeypatch.setattr(cf_mod, "Divera247ApiClient", lambda _k: client)
    assert await flow._test_access_key("k") == "Muster 7"
    client.async_close.assert_awaited()

    client.async_get_pull_all = AsyncMock(
        return_value=SimpleNamespace(success=False, data=None)
    )
    with pytest.raises(cf_mod.Divera247ApiCommunicationError):
        await flow._test_access_key("k")

    client.async_get_pull_all = AsyncMock(
        return_value=SimpleNamespace(
            success=True,
            data=SimpleNamespace(
                cluster=SimpleNamespace(name=None), ucr_active=None, ucr_default=None
            ),
        )
    )
    assert await flow._test_access_key("k") == "Unbekannt"
