"""Config flow for Haier SmartAir2."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .cloud import CloudAuthError, HaierCloudClient
from .const import (
    CONF_CLIENT_ID,
    CONF_LOCAL_IPS,
    CONF_PASSWORD,
    CONF_REGION,
    CONF_USERNAME,
    DEFAULT_REGION,
    DOMAIN,
    REGIONS,
    generate_client_id,
)

_LOGGER = logging.getLogger(__name__)


class HaierConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the user config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HaierOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            region = user_input.get(CONF_REGION, DEFAULT_REGION)
            gateway = REGIONS.get(region, REGIONS[DEFAULT_REGION])
            cloud = HaierCloudClient(
                self.hass, user_input[CONF_USERNAME], user_input[CONF_PASSWORD], gateway
            )
            try:
                await cloud.async_login()
            except CloudAuthError:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Haier config validation failed")
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
                self._abort_if_unique_id_configured()
                # per-installation gateway client id (never the app's / another user's)
                data = {**user_input, CONF_CLIENT_ID: generate_client_id()}
                return self.async_create_entry(
                    title=f"Haier ({user_input[CONF_USERNAME]})", data=data
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_REGION, default=DEFAULT_REGION): SelectSelector(
                    SelectSelectorConfig(
                        options=list(REGIONS.keys()),
                        mode=SelectSelectorMode.DROPDOWN,
                        translation_key="region",
                    )
                ),
                vol.Optional(CONF_LOCAL_IPS, default=""): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Ask for a replacement password for the existing account."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate the password, update the existing entry and reload it."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            conf = {**entry.data, **entry.options}
            region = conf.get(CONF_REGION, DEFAULT_REGION)
            cloud = HaierCloudClient(
                self.hass,
                entry.data[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                REGIONS.get(region, REGIONS[DEFAULT_REGION]),
                entry.data.get(CONF_CLIENT_ID),
            )
            try:
                await cloud.async_login()
            except CloudAuthError:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Haier reauthentication validation failed")
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
            description_placeholders={"username": entry.data[CONF_USERNAME]},
        )


class HaierOptionsFlow(OptionsFlow):
    """Let the user change region / local-device mapping without re-adding."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            if user_input != self.config_entry.options:
                self.hass.config_entries.async_update_entry(
                    self.config_entry, options=user_input
                )
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_REGION, default=current.get(CONF_REGION, DEFAULT_REGION)
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=list(REGIONS.keys()),
                        mode=SelectSelectorMode.DROPDOWN,
                        translation_key="region",
                    )
                ),
                vol.Optional(
                    CONF_LOCAL_IPS, default=current.get(CONF_LOCAL_IPS, "")
                ): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
