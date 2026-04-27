"""Tests for API wrapper module."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import custom_components.divera247.api as api_mod


@pytest.mark.anyio
async def test_client_init_and_raw_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Initialize wrapper client and expose raw client."""
    calls: dict[str, object] = {}

    class FakeClient:
        def __init__(self, auth: object) -> None:
            calls["auth"] = auth

    monkeypatch.setattr(api_mod, "Divera247Client", FakeClient)
    monkeypatch.setattr(api_mod, "RefreshingJwtAuth", lambda key: f"auth:{key}")

    client = api_mod.Divera247ApiClient("abc")
    assert calls["auth"] == "auth:abc"
    assert isinstance(client.raw_client, FakeClient)


@pytest.mark.anyio
async def test_async_close() -> None:
    """Close delegates to the wrapped client."""
    client = object.__new__(api_mod.Divera247ApiClient)
    raw = SimpleNamespace(aclose=AsyncMock())
    client._client = raw
    await client.async_close()
    raw.aclose.assert_awaited_once()


@pytest.mark.anyio
async def test_async_get_pull_all_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """pull/all success path validates and returns parsed payload."""
    client = object.__new__(api_mod.Divera247ApiClient)
    response = SimpleNamespace(json=lambda: {"ok": True})
    client._client = SimpleNamespace(get=AsyncMock(return_value=response))
    monkeypatch.setattr(
        api_mod.PullAllResponse,
        "model_validate",
        staticmethod(lambda payload: f"validated:{payload['ok']}"),
    )
    assert await client.async_get_pull_all() == "validated:True"


@pytest.mark.anyio
async def test_async_get_pull_all_error_mapping() -> None:
    """pull/all maps auth, API, and generic errors."""
    client = object.__new__(api_mod.Divera247ApiClient)
    client._client = SimpleNamespace(
        get=AsyncMock(side_effect=api_mod.DiveraAuthError("x"))
    )
    with pytest.raises(api_mod.Divera247ApiAuthError):
        await client.async_get_pull_all()

    client._client = SimpleNamespace(
        get=AsyncMock(side_effect=api_mod.DiveraAPIError("x"))
    )
    with pytest.raises(api_mod.Divera247ApiCommunicationError):
        await client.async_get_pull_all()

    client._client = SimpleNamespace(get=AsyncMock(side_effect=RuntimeError("x")))
    with pytest.raises(
        api_mod.Divera247ApiCommunicationError, match="Unexpected error fetching"
    ):
        await client.async_get_pull_all()


@pytest.mark.anyio
async def test_async_set_status_success_and_errors() -> None:
    """set_status forwards payload and maps wrapper exceptions."""
    client = object.__new__(api_mod.Divera247ApiClient)
    set_status = AsyncMock()
    client._client = SimpleNamespace(statusgeber=SimpleNamespace(set_status=set_status))
    await client.async_set_status(5, note="n", vehicle_id=7)
    set_status.assert_awaited_once()

    client._client = SimpleNamespace(
        statusgeber=SimpleNamespace(
            set_status=AsyncMock(side_effect=api_mod.DiveraAuthError("x"))
        )
    )
    with pytest.raises(api_mod.Divera247ApiAuthError):
        await client.async_set_status(1)

    client._client = SimpleNamespace(
        statusgeber=SimpleNamespace(
            set_status=AsyncMock(side_effect=api_mod.DiveraAPIError("x"))
        )
    )
    with pytest.raises(api_mod.Divera247ApiCommunicationError):
        await client.async_set_status(1)

    client._client = SimpleNamespace(
        statusgeber=SimpleNamespace(set_status=AsyncMock(side_effect=ValueError("x")))
    )
    with pytest.raises(
        api_mod.Divera247ApiCommunicationError, match="Unexpected error setting"
    ):
        await client.async_set_status(1)


@pytest.mark.anyio
async def test_async_get_vehicle_status_success_and_errors() -> None:
    """vehicle-status endpoint maps success and all error branches."""
    client = object.__new__(api_mod.Divera247ApiClient)
    getter = AsyncMock(return_value="ok")
    client._client = SimpleNamespace(pull=SimpleNamespace(get_vehicle_status=getter))
    assert await client.async_get_vehicle_status() == "ok"

    client._client = SimpleNamespace(
        pull=SimpleNamespace(
            get_vehicle_status=AsyncMock(side_effect=api_mod.DiveraAuthError("x"))
        )
    )
    with pytest.raises(api_mod.Divera247ApiAuthError):
        await client.async_get_vehicle_status()

    client._client = SimpleNamespace(
        pull=SimpleNamespace(
            get_vehicle_status=AsyncMock(side_effect=api_mod.DiveraAPIError("x"))
        )
    )
    with pytest.raises(api_mod.Divera247ApiCommunicationError):
        await client.async_get_vehicle_status()

    client._client = SimpleNamespace(
        pull=SimpleNamespace(get_vehicle_status=AsyncMock(side_effect=ValueError("x")))
    )
    with pytest.raises(
        api_mod.Divera247ApiCommunicationError,
        match="Unexpected error fetching DIVERA vehicle status data",
    ):
        await client.async_get_vehicle_status()
