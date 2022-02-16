"""Config flow for the MELCloud platform."""
from __future__ import annotations

import asyncio
from http import HTTPStatus

from aiohttp import ClientError, ClientResponseError, ClientSession
from async_timeout import timeout
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_EMAIL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_LOCAL
from .melview import MelViewAuthentication

APPVERSION = '5.3.1330'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_5) '
           'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.131 Safari/537.36'}
 


class FlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1
    
    def __init__(self):
        """Initialize."""
        self._errors = {}

    async def _create_entry(self, email: str, password: str, local: bool):
        """Register new entry."""
        await self.async_set_unique_id(email)
        self._abort_if_unique_id_configured({CONF_EMAIL: email})
        return self.async_create_entry(
            title=email, data={CONF_EMAIL: email, CONF_PASSWORD: password, CONF_LOCAL: local}
        )

    async def _create_client(
        self,
        email: str,
        *,
        password: str,
        local: bool 
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
                    {vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str, vol.Required(CONF_LOCAL) : bool}
                    ),
                    errors=self._errors,
                )

        return await self._create_entry(email, password, local)

    async def async_step_user(self, user_input=None):
        """User initiated config flow."""
        self._errors = {}
        
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str, vol.Required(CONF_LOCAL) : bool}
                ),
            )
        email = user_input[CONF_EMAIL]
        return await self._create_client(user_input[CONF_EMAIL], password=user_input[CONF_PASSWORD], local=user_input[CONF_LOCAL])

    async def async_step_import(self, user_input):
        """Import a config entry."""
        return await self._create_client(
            user_input[CONF_EMAIL], password=user_input[CONF_PASSWORD], local=user_input[CONF_LOCAL]
        )
