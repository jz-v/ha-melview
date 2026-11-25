"""Config flow for the MelView platform."""

from __future__ import annotations

import logging

from aiohttp import ClientError
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .const import CONF_LOCAL, CONF_SENSOR, DOMAIN
from .melview import MelViewAuthentication, MelViewError

_LOGGER = logging.getLogger(__name__)

PASSWORD_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
)
USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
        ),
        vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
        vol.Required(CONF_LOCAL, default=True): bool,
        vol.Required(CONF_SENSOR, default=True): bool,
    }
)
PASSWORD_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR})


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

    async def _async_login(
        self, email: str, password: str
    ) -> tuple[MelViewAuthentication, str | None]:
        """Log in to MelView; return the client and an error key if it failed."""
        auth = MelViewAuthentication(
            email, password, async_get_clientsession(self.hass)
        )
        try:
            valid = await auth.async_login()
        except (TimeoutError, ClientError, MelViewError) as err:
            _LOGGER.error("Unable to log in to MelView: %r", err)
            return auth, "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error logging in to MelView")
            return auth, "unknown"
        return auth, None if valid else "invalid_auth"

    async def _create_client(
        self,
        email: str,
        *,
        password: str,
        local: bool,
        sensor: bool,
    ):
        """Create client and validate credentials."""
        auth, error = await self._async_login(email, password)
        if error is None:
            units = auth.number_units()
            if units is False:
                error = "unknown"
            elif units == 0:
                error = "no_units"
            else:
                return await self._create_entry(email, password, local, sensor)

        self._errors = {"base": error}
        # Show the form again with what the user entered, except the password
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA,
                {CONF_EMAIL: email, CONF_LOCAL: local, CONF_SENSOR: sensor},
            ),
            errors=self._errors,
        )

    async def async_step_user(self, user_input=None):
        """User initiated config flow."""
        self._errors = {}

        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=USER_SCHEMA)

        email = user_input[CONF_EMAIL].strip().lower()
        return await self._create_client(
            email,
            password=user_input[CONF_PASSWORD],
            local=user_input[CONF_LOCAL],
            sensor=user_input[CONF_SENSOR],
        )

    async def _async_step_new_password(self, step_id: str, entry, user_input):
        """Ask for the account's password and store it once MelView accepts it."""
        self._errors = {}
        email = entry.data[CONF_EMAIL]

        if user_input is not None:
            _, error = await self._async_login(email, user_input[CONF_PASSWORD])
            if error is None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
            self._errors["base"] = error

        return self.async_show_form(
            step_id=step_id,
            data_schema=PASSWORD_SCHEMA,
            errors=self._errors,
            description_placeholders={"email": email},
        )

    async def async_step_reconfigure(self, user_input=None):
        """Reconfigure / change password."""
        return await self._async_step_new_password(
            "reconfigure", self._get_reconfigure_entry(), user_input
        )

    async def async_step_reauth(self, entry_data):
        """Start re-authentication when the stored credentials are rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Ask for the new password and validate it."""
        return await self._async_step_new_password(
            "reauth_confirm", self._get_reauth_entry(), user_input
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlowWithReload):
    """Handle options flow for MelView; saving changed options reloads the entry."""

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
