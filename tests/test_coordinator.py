"""Tests for the DIVERA data coordinator."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.divera247.api import Divera247ApiAuthError, Divera247ApiError
from custom_components.divera247.coordinator import Divera247DataUpdateCoordinator

if TYPE_CHECKING:
    from divera247.models.pull import PullData


def _make_coordinator(
    client: object,
    vehicle_cache: dict[str, object] | None = None,
) -> Divera247DataUpdateCoordinator:
    """Build a coordinator instance without Home Assistant runtime wiring."""
    coordinator = object.__new__(Divera247DataUpdateCoordinator)
    coordinator.config_entry = SimpleNamespace(
        runtime_data=SimpleNamespace(client=client)
    )
    coordinator.vehicle_status_by_id = vehicle_cache or {}
    return cast("Divera247DataUpdateCoordinator", coordinator)


@pytest.mark.anyio
async def test_async_update_data_populates_vehicle_cache() -> None:
    """Successful refresh updates pull data and vehicle cache."""
    pull_data = cast("PullData", SimpleNamespace())
    vehicle_1 = SimpleNamespace(id=1)
    vehicle_without_id = SimpleNamespace(id=None)
    client = SimpleNamespace(
        async_get_pull_all=AsyncMock(
            return_value=SimpleNamespace(success=True, data=pull_data)
        ),
        async_get_vehicle_status=AsyncMock(
            return_value=SimpleNamespace(
                success=True, data=[vehicle_1, vehicle_without_id]
            )
        ),
    )
    coordinator = _make_coordinator(client)

    result = await coordinator._async_update_data()

    assert result is pull_data
    assert coordinator.vehicle_status_by_id == {"1": vehicle_1}


@pytest.mark.anyio
async def test_async_update_data_maps_auth_error() -> None:
    """Auth errors are surfaced as ConfigEntryAuthFailed."""
    client = SimpleNamespace(
        async_get_pull_all=AsyncMock(side_effect=Divera247ApiAuthError("bad token")),
        async_get_vehicle_status=AsyncMock(),
    )
    coordinator = _make_coordinator(client)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


@pytest.mark.anyio
async def test_async_update_data_raises_on_pull_success_false() -> None:
    """Coordinator fails refresh when pull/all returns success=false."""
    client = SimpleNamespace(
        async_get_pull_all=AsyncMock(
            return_value=SimpleNamespace(success=False, data=None)
        ),
        async_get_vehicle_status=AsyncMock(),
    )
    coordinator = _make_coordinator(client)

    with pytest.raises(UpdateFailed, match="success=false"):
        await coordinator._async_update_data()


@pytest.mark.anyio
async def test_async_update_data_raises_if_vehicle_status_fails_initially() -> None:
    """Initial setup fails if vehicle-status cannot be fetched."""
    pull_data = cast("PullData", SimpleNamespace())
    client = SimpleNamespace(
        async_get_pull_all=AsyncMock(
            return_value=SimpleNamespace(success=True, data=pull_data)
        ),
        async_get_vehicle_status=AsyncMock(side_effect=Divera247ApiError("timeout")),
    )
    coordinator = _make_coordinator(client)

    with pytest.raises(UpdateFailed, match="initial setup"):
        await coordinator._async_update_data()


@pytest.mark.anyio
async def test_async_update_data_maps_non_auth_pull_error() -> None:
    """Generic API errors are surfaced as UpdateFailed."""
    client = SimpleNamespace(
        async_get_pull_all=AsyncMock(side_effect=Divera247ApiError("boom")),
        async_get_vehicle_status=AsyncMock(),
    )
    coordinator = _make_coordinator(client)

    with pytest.raises(UpdateFailed, match="boom"):
        await coordinator._async_update_data()


@pytest.mark.anyio
async def test_async_update_data_keeps_vehicle_cache_on_transient_error() -> None:
    """Existing vehicle cache is preserved on vehicle-status refresh errors."""
    pull_data = cast("PullData", SimpleNamespace())
    cached_vehicle = SimpleNamespace(id=7)
    client = SimpleNamespace(
        async_get_pull_all=AsyncMock(
            return_value=SimpleNamespace(success=True, data=pull_data)
        ),
        async_get_vehicle_status=AsyncMock(side_effect=Divera247ApiError("temporary")),
    )
    coordinator = _make_coordinator(client, vehicle_cache={"7": cached_vehicle})

    result = await coordinator._async_update_data()

    assert result is pull_data
    assert coordinator.vehicle_status_by_id == {"7": cached_vehicle}


@pytest.mark.anyio
async def test_async_update_data_raises_when_pull_has_no_data() -> None:
    """Missing pull data should fail update."""
    client = SimpleNamespace(
        async_get_pull_all=AsyncMock(
            return_value=SimpleNamespace(success=True, data=None)
        ),
        async_get_vehicle_status=AsyncMock(),
    )
    coordinator = _make_coordinator(client)

    with pytest.raises(UpdateFailed, match="returned no data"):
        await coordinator._async_update_data()


@pytest.mark.anyio
async def test_async_update_data_raises_if_first_vehicle_success_false() -> None:
    """Initial setup fails when vehicle endpoint reports success false."""
    pull_data = cast("PullData", SimpleNamespace())
    client = SimpleNamespace(
        async_get_pull_all=AsyncMock(
            return_value=SimpleNamespace(success=True, data=pull_data)
        ),
        async_get_vehicle_status=AsyncMock(
            return_value=SimpleNamespace(success=False, data=[])
        ),
    )
    coordinator = _make_coordinator(client)

    with pytest.raises(UpdateFailed, match="vehicle-status API reported success=false"):
        await coordinator._async_update_data()


@pytest.mark.anyio
async def test_async_update_data_keeps_cache_if_vehicle_success_false_later() -> None:
    """Existing cache survives non-success vehicle status response."""
    pull_data = cast("PullData", SimpleNamespace())
    cached_vehicle = SimpleNamespace(id=9)
    client = SimpleNamespace(
        async_get_pull_all=AsyncMock(
            return_value=SimpleNamespace(success=True, data=pull_data)
        ),
        async_get_vehicle_status=AsyncMock(
            return_value=SimpleNamespace(success=False, data=[])
        ),
    )
    coordinator = _make_coordinator(client, vehicle_cache={"9": cached_vehicle})

    result = await coordinator._async_update_data()

    assert result is pull_data
    assert coordinator.vehicle_status_by_id == {"9": cached_vehicle}
