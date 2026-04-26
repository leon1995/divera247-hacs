"""
Config flow for the DIVERA 24/7 integration.

Only an access key is collected. The key is validated by attempting a single
``pull/all`` request against the live API; on success we derive a friendly
entry title from the fire station/cluster name plus active UCR ID.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from custom_components.divera247.api import (
    Divera247ApiAuthError,
    Divera247ApiClient,
    Divera247ApiCommunicationError,
    Divera247ApiError,
)
from custom_components.divera247.const import CONF_ACCESS_KEY, DOMAIN, LOGGER

if TYPE_CHECKING:
    from collections.abc import Mapping


class Divera247ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration step."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: Mapping[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the access-key entry step."""
        errors: dict[str, str] = {}
        title = "DIVERA 24/7"

        if user_input is not None:
            access_key = user_input[CONF_ACCESS_KEY].strip()
            try:
                title = await self._test_access_key(access_key)
            except Divera247ApiAuthError as exc:
                LOGGER.warning("DIVERA auth failed: %s", exc)
                errors["base"] = "invalid_auth"
            except Divera247ApiCommunicationError as exc:
                LOGGER.error("DIVERA connection error: %s", exc)
                errors["base"] = "cannot_connect"
            except Divera247ApiError as exc:
                LOGGER.exception("Unexpected DIVERA error: %s", exc)
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(access_key)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=title,
                    data={CONF_ACCESS_KEY: access_key},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ACCESS_KEY,
                        default=(user_input or {}).get(CONF_ACCESS_KEY, vol.UNDEFINED),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                        ),
                    ),
                },
            ),
            errors=errors,
        )

    async def _test_access_key(self, access_key: str) -> str:
        """
        Call the API with the given key and return a friendly title.

        The title follows ``Feuerwehr <cluster_name> <ucr_id>`` so generated
        entity IDs are stable and not based on personal user names.
        """
        client = await self.hass.async_add_executor_job(
            Divera247ApiClient,
            access_key,
        )
        try:
            response = await client.async_get_pull_all()
        finally:
            await client.async_close()

        if not response.success or response.data is None:
            msg = "DIVERA API reported success=false during validation"
            raise Divera247ApiCommunicationError(
                msg,
            )

        data = response.data
        cluster_name = (
            data.cluster.name
            if data.cluster is not None and data.cluster.name
            else "Unbekannt"
        )
        title_base = cluster_name.strip()
        ucr_id = data.ucr_active or data.ucr_default
        if ucr_id is not None:
            return f"{title_base} {ucr_id}"
        return title_base
