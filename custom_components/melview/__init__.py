"""The MelView integration."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, CONF_LOCAL, CONF_HALFSTEP
from .melview import MelViewAuthentication, MelView
from .climate import MelViewClimate
from .switch import MelViewZoneSwitch

_LOGGER = logging.getLogger(__name__)

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=60)

PLATFORMS = [Platform.CLIMATE, Platform.SWITCH]

CONF_LANGUAGE = "language"
CONFIG_SCHEMA = vol.Schema(
    vol.All(
        cv.deprecated(DOMAIN),
        {
            DOMAIN: vol.Schema(
                {
                    vol.Required(CONF_EMAIL): cv.string,
                    vol.Required(CONF_PASSWORD): cv.string,
                    vol.Required(CONF_LOCAL): cv.boolean,
                    vol.Required(CONF_HALFSTEP): cv.boolean,
                }
            )
        },
    ),
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Establish connection with Melview."""
    if DOMAIN not in config:
        return True

    email = config[DOMAIN][CONF_EMAIL]
    password = config[DOMAIN][CONF_PASSWORD]
    local = config[DOMAIN][CONF_LOCAL]
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data={CONF_EMAIL: email, CONF_PASSWORD: password, CONF_LOCAL: local},
        )
    )
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Establish connection with MelView."""
    await async_migrate_entry(hass, entry)
    conf = entry.data
    mv_auth = MelViewAuthentication(conf[CONF_EMAIL], conf[CONF_PASSWORD])
    result = await mv_auth.asynclogin()
    if not result:
        _LOGGER.error('login combination')
        return False
    _LOGGER.debug('Got auth')
    melview = MelView(mv_auth,localcontrol=conf[CONF_LOCAL])
    device_list = []
    _LOGGER.debug('Getting data')
    
    devices = await melview.async_get_devices_list()
    for device in devices:
        await device.async_refresh()
        _LOGGER.debug("Device: "+ device.get_friendly_name())
        device_list.append(device)
        # for zone in device.get_zones():
            # device_list.append(MelViewZoneSwitch(zone, device))
    _LOGGER.debug('Got data')

    hass.data.setdefault(DOMAIN, {}).update({entry.entry_id: device_list})
    # hass.config_entries.async_setup_platforms(entry, PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )
    hass.data[DOMAIN].pop(config_entry.entry_id)
    if not hass.data[DOMAIN]:
        hass.data.pop(DOMAIN)
    return unload_ok

async def async_migrate_entry(hass, config_entry):
    """Migrate old config entry."""
    data = {**config_entry.data}
    options = config_entry.options
    
    if CONF_LOCAL in options:
        data[CONF_LOCAL] = options[CONF_LOCAL]
    if CONF_HALFSTEP in options:
        data[CONF_HALFSTEP] = options[CONF_HALFSTEP]
    
    hass.config_entries.async_update_entry(config_entry, data=data)
    return True
