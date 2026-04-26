"""
Config flow for the DIVERA 24/7 integration.

Only an access key is collected. The key is validated by attempting a single
``pull/all`` request against the live API; on success we use the account's
email (from the payload) as unique ID so the same key cannot be configured
twice.
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

        The title prefers ``firstname lastname`` from the user payload, falls
        back to the account email and finally to a generic string so the
        entry always has a sensible display name.
        """
        client = Divera247ApiClient(access_key=access_key)
        try:
            response = await client.async_get_pull_all()
        finally:
            await client.async_close()

        if not response.success or response.data is None:
            msg = "DIVERA API reported success=false during validation"
            raise Divera247ApiCommunicationError(
                msg,
            )

        user = response.data.user
        if user is not None:
            name = " ".join(
                part for part in (user.firstname, user.lastname) if part
            ).strip()
            if name:
                return name
            if user.email:
                return user.email
        return "DIVERA 24/7"
