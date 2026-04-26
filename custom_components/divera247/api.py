"""
Thin wrapper around the ``divera247`` Python library.

The wrapper owns a :class:`divera247.Divera247Client` (which in turn owns its
own :class:`httpx.AsyncClient`) for the lifetime of a config entry and turns
library exceptions into a small set of integration-specific errors so the rest
of Home Assistant only deals with our types.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from divera247 import (
    Divera247Client,
    DiveraAPIError,
    DiveraAuthError,
    RefreshingJwtAuth,
)
from divera247.models.statusgeber import StatusgeberPayload, StatusgeberStatus

if TYPE_CHECKING:
    from divera247.models.pull import PullAllResponse, VehicleStatusResponse


class Divera247ApiError(Exception):
    """Base error raised by the integration's API wrapper."""


class Divera247ApiAuthError(Divera247ApiError):
    """Raised when the access key is rejected by the server."""


class Divera247ApiCommunicationError(Divera247ApiError):
    """Raised when the API cannot be reached or returns an unexpected error."""


class Divera247ApiClient:
    """Async wrapper that talks to the DIVERA 24/7 REST API."""

    def __init__(self, access_key: str) -> None:
        """
        Create a new client using access-key backed JWT auth.

        The REST and WebSocket APIs both authenticate via bearer JWT tokens.
        ``RefreshingJwtAuth`` transparently fetches and refreshes that JWT
        using the configured access key, so callers do not need to manage
        token lifecycles manually.
        """
        self._access_key = access_key
        self._client = Divera247Client(auth=RefreshingJwtAuth(access_key))

    @property
    def raw_client(self) -> Divera247Client:
        """
        Return the underlying :class:`divera247.Divera247Client`.

        Exposed so the WebSocket listener can reuse the same httpx session
        and auth flow as the REST wrapper.
        """
        return self._client

    async def async_close(self) -> None:
        """Close the underlying HTTP session."""
        await self._client.aclose()

    async def async_get_pull_all(self) -> PullAllResponse:
        """
        Fetch the full ``/api/v2/pull/all`` payload.

        This single request returns the current user status, cluster metadata,
        alarm/news/event items and the active UCR, which is enough to power
        all of the read-only entities exposed by the integration.
        """
        try:
            return await self._client.pull.get_all()
        except DiveraAuthError as exc:
            raise Divera247ApiAuthError(str(exc)) from exc
        except DiveraAPIError as exc:
            raise Divera247ApiCommunicationError(str(exc)) from exc
        except Exception as exc:
            msg = f"Unexpected error fetching DIVERA pull data: {exc}"
            raise Divera247ApiCommunicationError(msg) from exc

    async def async_set_status(
        self,
        status_id: int,
        *,
        note: str | None = None,
        vehicle_id: int | None = None,
    ) -> None:
        """Set the current user's status via ``/api/v2/statusgeber/set-status``."""
        payload = StatusgeberPayload(
            Status=StatusgeberStatus(
                id=status_id,
                note=note,
                vehicle=vehicle_id,
            ),
        )
        try:
            await self._client.statusgeber.set_status(payload)
        except DiveraAuthError as exc:
            raise Divera247ApiAuthError(str(exc)) from exc
        except DiveraAPIError as exc:
            raise Divera247ApiCommunicationError(str(exc)) from exc
        except Exception as exc:
            msg = f"Unexpected error setting DIVERA status: {exc}"
            raise Divera247ApiCommunicationError(msg) from exc

    async def async_get_vehicle_status(self) -> VehicleStatusResponse:
        """Fetch ``/api/v2/pull/vehicle-status`` data."""
        try:
            return await self._client.pull.get_vehicle_status()
        except DiveraAuthError as exc:
            raise Divera247ApiAuthError(str(exc)) from exc
        except DiveraAPIError as exc:
            raise Divera247ApiCommunicationError(str(exc)) from exc
        except Exception as exc:
            msg = f"Unexpected error fetching DIVERA vehicle status data: {exc}"
            raise Divera247ApiCommunicationError(msg) from exc
