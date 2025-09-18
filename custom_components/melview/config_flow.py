"""Config flow for the Melview platform."""
from __future__ import annotations

import asyncio
import logging

from aiohttp import ClientError
from async_timeout import timeout
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_EMAIL
from homeassistant.core import callback

from .const import DOMAIN, CONF_LOCAL, CONF_SENSOR
from .melview import MelViewAuthentication

_LOGGER = logging.getLogger(__name__)


class FlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    def __init__(self):
        """Initialize."""
        self._errors: dict[str, str] = {}

    async def _create_entry(self, email: str, password: str, local: bool, sensor: bool):
        """Register new entry."""
        await self.async_set_unique_id(email)
        self._abort_if_unique_id_configured({CONF_EMAIL: email})
        return self.async_create_entry(
            title=email,
            data={
                CONF_EMAIL: email,
                CONF_PASSWORD: password,
            },
            options={
                CONF_LOCAL: local,
                CONF_SENSOR: sensor,
            },
        )

    async def _create_client(
        self,
        email: str,
        *,
        password: str,
        local: bool,
        sensor: bool,
    ):
        """Create client and validate credentials."""
        if password is None and email is None:
            raise ValueError(
                "Invalid internal state. Called without either password or email"
            )

        valid = False
        try:
            async with timeout(15):
                auth = MelViewAuthentication(email, password)
                valid = await auth.asynclogin()
        except (ClientError, asyncio.TimeoutError) as e:
            _LOGGER.error("MelView auth error during config flow: %r", e)
            valid = False
        except Exception:  # pragma: no cover - unexpected
            _LOGGER.exception("Unexpected MelView error during config flow")
            valid = False

        if not valid:
            self._errors = {"base": "invalid_auth"}
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_EMAIL, default=email): str,
                        vol.Required(CONF_PASSWORD): str,
                        vol.Required(CONF_LOCAL, default=True): bool,
                        vol.Required(CONF_SENSOR, default=True): bool,
                    }
                ),
                errors=self._errors,
            )

        return await self._create_entry(email, password, local, sensor)

    async def async_step_user(self, user_input=None):
        """User initiated config flow."""
        self._errors = {}

        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_EMAIL): str,
                        vol.Required(CONF_PASSWORD): str,
                        vol.Required(CONF_LOCAL, default=True): bool,
                        vol.Required(CONF_SENSOR, default=True): bool,
                    }
                ),
            )

        email = user_input[CONF_EMAIL].strip().lower()
        return await self._create_client(
            email,
            password=user_input[CONF_PASSWORD],
            local=user_input[CONF_LOCAL],
            sensor=user_input[CONF_SENSOR],
        )

    async def async_step_reconfigure(self, user_input=None):
        """Reconfigure / change password."""
        self._errors = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        email = entry.data[CONF_EMAIL]

        if user_input is not None:
            valid = False
            try:
                async with timeout(15):
                    auth = MelViewAuthentication(email, user_input[CONF_PASSWORD])
                    valid = await auth.asynclogin()
            except (ClientError, asyncio.TimeoutError) as e:
                _LOGGER.error("MelView auth error during reconfigure: %r", e)
                valid = False

            if not valid:
                self._errors["base"] = "invalid_auth"
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
                    errors=self._errors,
                    description_placeholders={"email": email},
                )

            data = dict(entry.data)
            data[CONF_PASSWORD] = user_input[CONF_PASSWORD]

            return self.async_update_reload_and_abort(
                entry, data=data, reason="password_change_success"
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"email": email},
        )

    async def async_step_reauth(self, user_input=None):
        """Handle re-authentication when credentials are invalid."""
        self._errors = {}

        entry = None
        if self.context.get("entry_id"):
            entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="unknown")

        email = entry.data.get(CONF_EMAIL, "")

        if user_input is not None:
            try:
                async with timeout(15):
                    auth = MelViewAuthentication(email, user_input[CONF_PASSWORD])
                    valid = await auth.asynclogin()
            except (ClientError, asyncio.TimeoutError) as e:
                _LOGGER.error("MelView auth error during reauth: %r", e)
                valid = False

            if not valid:
                self._errors["base"] = "invalid_auth"
                return self.async_show_form(
                    step_id="reauth",
                    data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
                    errors=self._errors,
                    description_placeholders={"email": email},
                )

            new_data = dict(entry.data)
            new_data[CONF_PASSWORD] = user_input[CONF_PASSWORD]
            self.hass.config_entries.async_update_entry(entry, data=new_data)
            await self.hass.config_entries.async_reload(entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"email": email},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for MelView."""

    def __init__(self, config_entry):
        """Initialize MelView options flow."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        local = True
        sensor = True

        if CONF_LOCAL in self._config_entry.data:
            local = self._config_entry.data[CONF_LOCAL]
        if CONF_SENSOR in self._config_entry.data:
            sensor = self._config_entry.data[CONF_SENSOR]

        if self._config_entry.options:
            if CONF_LOCAL in self._config_entry.options:
                local = self._config_entry.options[CONF_LOCAL]
            if CONF_SENSOR in self._config_entry.options:
                sensor = self._config_entry.options[CONF_SENSOR]

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LOCAL, default=local): bool,
                    vol.Required(CONF_SENSOR, default=sensor): bool,
                }
            ),
        )