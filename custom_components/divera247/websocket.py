"""
WebSocket push-event listener for DIVERA 24/7.

Subscribes to ``wss://ws.divera247.com/ws`` via
:func:`divera247.websocket.stream_websocket` in a background task and dispatches
every received event to the coordinator. The poll loop in
:mod:`.coordinator` stays in place as a safety net at a much longer interval;
real-time updates arrive through this listener.

Event handling:

* ``UserStatusEvent`` -- the status block contains the full ``PullStatusData`` for
  the affected UCR, so we patch ``coordinator.data.status`` in place and push
  the update out via :meth:`DataUpdateCoordinator.async_set_updated_data`
  without issuing another HTTP request.
* ``ClusterPullEvent`` -- the cluster resource referenced in the event has
  changed; we schedule a standard coordinator refresh so the affected block
  (alarms, news, events, ...) is re-fetched once.
* ``cluster-vehicle`` events -- vehicle/FMS updates trigger a coordinator refresh.
* ``UnknownEvent`` -- logged so missing models can be added upstream later.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any

from custom_components.divera247.const import LOGGER
from divera247.websocket import (
    ClusterPullEvent,
    UserStatusEvent,
    WebSocketAuthenticationError,
    stream_websocket,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from custom_components.divera247.api import Divera247ApiClient
    from custom_components.divera247.coordinator import Divera247DataUpdateCoordinator


class Divera247WebSocketListener:
    """
    Background task that keeps a DIVERA push-event subscription alive.

    :param hass: Home Assistant instance, used to own the background task.
    :param coordinator: The coordinator whose ``data`` we mutate / refresh.
    :param api_client: Wrapper whose underlying ``Divera247Client`` is reused
        (same auth + httpx session).
    :param ucr_id: Optional UCR to scope the subscription to. If ``None``
        the server falls back to the default UCR for the access key.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: Divera247DataUpdateCoordinator,
        api_client: Divera247ApiClient,
        ucr_id: int | None,
    ) -> None:
        """Store dependencies; the task only starts on :meth:`async_start`."""
        self._hass = hass
        self._coordinator = coordinator
        self._api_client = api_client
        self._ucr_id = ucr_id
        self._task: asyncio.Task[None] | None = None

    def async_start(self) -> None:
        """Create the background task that consumes the WS stream."""
        if self._task is not None and not self._task.done():
            return
        self._task = self._hass.async_create_background_task(
            self._run(),
            name=f"divera247 ws listener ucr={self._ucr_id}",
        )

    async def async_stop(self) -> None:
        """Cancel and await the background task, if it is running."""
        task = self._task
        self._task = None
        if task is None or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _run(self) -> None:
        """Consume events until cancelled or auth becomes unrecoverable."""
        try:
            async for event in stream_websocket(
                self._api_client.raw_client,
                ucr_id=self._ucr_id,
            ):
                self._dispatch(event)
        except WebSocketAuthenticationError as exc:
            LOGGER.error("DIVERA WebSocket authentication failed permanently: %s", exc)
        except Exception as exc:  # noqa: BLE001
            if self._is_shutdown_exception_group(exc):
                LOGGER.debug("DIVERA WebSocket listener stopped during shutdown")
                return
            raise
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            LOGGER.exception("DIVERA WebSocket listener crashed; giving up")

    def _dispatch(
        self,
        event: Any,
    ) -> None:
        """Route a parsed WS event to the coordinator."""
        if isinstance(event, UserStatusEvent):
            self._apply_user_status(event)
            return
        if isinstance(event, ClusterPullEvent) or event.type == "cluster-vehicle":
            LOGGER.debug(
                "DIVERA websocket change event (%s); refreshing",
                event.type,
            )
            self._hass.async_create_task(
                self._coordinator.async_request_refresh(),
            )
            return
        LOGGER.debug("DIVERA unknown WebSocket event: type=%s", event.type)

    @staticmethod
    def _is_shutdown_exception_group(exc: BaseException) -> bool:
        """Return ``True`` if ``exc`` only contains known WS shutdown errors."""
        nested_exceptions = getattr(exc, "exceptions", None)
        if not isinstance(nested_exceptions, tuple):
            return False
        for nested in nested_exceptions:
            if isinstance(getattr(nested, "exceptions", None), tuple):
                if not Divera247WebSocketListener._is_shutdown_exception_group(nested):
                    return False
                continue
            if not isinstance(nested, RuntimeError):
                return False
            if "cancel scope" not in str(nested):
                return False
        return True

    def _apply_user_status(self, event: UserStatusEvent) -> None:
        """Patch the cached status in place and notify listeners."""
        data = self._coordinator.data
        if data is None:
            self._hass.async_create_task(
                self._coordinator.async_request_refresh(),
            )
            return
        data.status = event.status
        self._coordinator.async_set_updated_data(data)
