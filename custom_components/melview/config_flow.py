"""Config flow for the MELCloud platform."""
from __future__ import annotations

import asyncio
from http import HTTPStatus

from aiohttp import ClientError, ClientResponseError, ClientSession
from async_timeout import timeout
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_EMAIL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_LOCAL, APPVERSION, HEADERS, CONF_HALFSTEP
from .melview import MelViewAuthentication

class FlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1
    
    def __init__(self):
        """Initialize."""
        self._errors = {}

    async def _create_entry(self, email: str, password: str, local: bool, halfstep: bool):
        """Register new entry."""
        await self.async_set_unique_id(email)
        self._abort_if_unique_id_configured({CONF_EMAIL: email})
        return self.async_create_entry(
            title=email, data={CONF_EMAIL: email, CONF_PASSWORD: password, CONF_LOCAL: local, CONF_HALFSTEP: halfstep}
        )

    async def _create_client(
        self,
        email: str,
        *,
        password: str,
        local: bool,
        halfstep: bool 
    ):
        """Create client."""
        if password is None and email is None:
            raise ValueError(
                "Invalid internal state. Called without either password or email"
            )

        valid=False
        async with ClientSession() as session:
            resp = await session.post('https://api.melview.net/api/login.aspx',
                    json={'user': email, 'pass': password,
                          'appversion': APPVERSION},
                    headers=HEADERS) 
            if resp.status == 200:
                cks = resp.cookies
                if 'auth' in cks:
                    cookie = cks['auth']
                    if cookie != None  and cookie.value and len(cookie.value)>5:
                        valid=True
        if not valid:
            self._errors = {"base": "invalid_auth"}
            return self.async_show_form(
                    step_id="user",
                    data_schema=vol.Schema(
                    {vol.Required(CONF_EMAIL, default=email): str,
                     vol.Required(CONF_PASSWORD): str,
                     vol.Required(CONF_LOCAL, default=True) : bool,
                     vol.Required(CONF_HALFSTEP, default=True): bool}
                    ),
                    errors=self._errors,
                )

        return await self._create_entry(email, password, local, halfstep)

    async def async_step_user(self, user_input=None):
        """User initiated config flow."""
        self._errors = {}
        
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Required(CONF_LOCAL, default=True) : bool,
                    vol.Required(CONF_HALFSTEP, default=True): bool}
                ),
            )
        email = user_input[CONF_EMAIL]
        return await self._create_client(user_input[CONF_EMAIL], password=user_input[CONF_PASSWORD], local=user_input[CONF_LOCAL], halfstep=user_input[CONF_HALFSTEP])

    async def async_step_import(self, user_input):
        """Import a config entry."""
        return await self._create_client(
            user_input[CONF_EMAIL], password=user_input[CONF_PASSWORD], local=user_input[CONF_LOCAL], halfstep=user_input[CONF_HALFSTEP]
        )
    
    async def async_step_reconfigure(self, user_input=None):
        """Reconfigure / change password."""
        self._errors = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        email = entry.data[CONF_EMAIL]

        if user_input is not None:
            valid = False
            async with ClientSession() as session:
                try:
                    resp = await session.post('https://api.melview.net/api/login.aspx',
                        json={'user': email, 
                            'pass': user_input[CONF_PASSWORD],
                            'appversion': APPVERSION},
                        headers=HEADERS)
                    if resp.status == 200:
                        cks = resp.cookies
                        if 'auth' in cks:
                            cookie = cks['auth']
                            if cookie != None and cookie.value and len(cookie.value) > 5:
                                valid = True
                except (ClientError, asyncio.TimeoutError):
                    valid = False

            if not valid:
                self._errors["base"] = "invalid_auth"
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=vol.Schema(
                        {vol.Required(CONF_PASSWORD): str}
                    ),
                    errors=self._errors,
                    description_placeholders={"email": email}
                )
            
            data = dict(entry.data)
            data[CONF_PASSWORD] = user_input[CONF_PASSWORD]

            return self.async_update_reload_and_abort(
                entry,
                data=data,
                reason="password_change_success"
            )
        
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {vol.Required(CONF_PASSWORD): str}
            ),
            description_placeholders={"email": email},
        )
    
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for melview."""
    
    def __init__(self, config_entry):
        """Initialize melview options flow."""
        self.config_entry = config_entry
        
    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        
        local = self.config_entry.options.get(CONF_LOCAL, False)
        halfstep = self.config_entry.options.get(CONF_HALFSTEP, False)
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LOCAL, default=self.config_entry.options.get(CONF_LOCAL, False)): bool,
                    vol.Required(CONF_HALFSTEP, default=self.config_entry.options.get(CONF_HALFSTEP, False)): bool
                }
            ),
        )