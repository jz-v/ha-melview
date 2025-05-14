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

from .const import DOMAIN, CONF_LOCAL, CONF_HALFSTEP, CONF_SENSOR
from .melview import MelViewAuthentication, MelView
from .climate import MelViewClimate
from .switch import MelViewZoneSwitch
from .coordinator import MelViewCoordinator

_LOGGER = logging.getLogger(__name__)

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=60)

PLATFORMS = [Platform.CLIMATE, Platform.SWITCH, Platform.SENSOR]

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
                    vol.Required(CONF_SENSOR): cv.boolean,
                }
            )
        },
    ),
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Establish connection with MelView."""
    if DOMAIN not in config:
        return True

    email = config[DOMAIN][CONF_EMAIL]
    password = config[DOMAIN][CONF_PASSWORD]
    local = config[DOMAIN][CONF_LOCAL]
    sensor = config[DOMAIN][CONF_SENSOR]
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data={CONF_EMAIL: email, CONF_PASSWORD: password, CONF_LOCAL: local, CONF_SENSOR: sensor}
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
        coordinator = MelViewCoordinator(hass, entry, device)
        # Prime the coordinator’s data cache
        await coordinator.async_config_entry_first_refresh()
        _LOGGER.debug("Device: " + device.get_friendly_name())
        device_list.append(coordinator)
    
    # Store coordinators by entry_id
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = device_list

    # Set up sensor, climate, and switch platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
  
    _LOGGER.debug('Set up coordinator(s)')
    # hass.data.setdefault(DOMAIN, {}).update({entry.entry_id: device_list})
    # await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
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
    if CONF_SENSOR in options:
        data[CONF_SENSOR] = options[CONF_SENSOR]
    
    hass.config_entries.async_update_entry(config_entry, data=data)
    return True
