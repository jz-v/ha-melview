"""The MelView integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    ConfigEntryNotReady,
)
from homeassistant.helpers import issue_registry as ir
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_LOCAL, CONF_SENSOR
from .melview import MelViewAuthentication, MelView
from .coordinator import MelViewCoordinator

type MelviewConfigEntry = ConfigEntry[list[MelViewCoordinator]]

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE, Platform.SWITCH, Platform.SENSOR, Platform.FAN]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up MelView; YAML is no longer supported (warn once if present)."""
    if DOMAIN in config:
        hass.data.setdefault(DOMAIN, {})
        if not hass.data[DOMAIN].get("_yaml_warned"):
            _LOGGER.warning(
                "YAML configuration for %s is no longer supported and will be ignored. "
                "Please remove the 'melview:' section from configuration.yaml and use the UI.",
                DOMAIN,
            )
            hass.data[DOMAIN]["_yaml_warned"] = True
    return True


async def async_setup_entry(hass: HomeAssistant, entry: MelviewConfigEntry) -> bool:
    """Establish connection with MelView."""
    await async_migrate_entry(hass, entry)
    conf = entry.data
    options = entry.options
    mv_auth = MelViewAuthentication(conf[CONF_EMAIL], conf[CONF_PASSWORD])
    result = await mv_auth.asynclogin()
    if not result:
        _LOGGER.error("MelView authentication failed for %s", conf[CONF_EMAIL])
        ir.async_create_issue(
            hass,
            DOMAIN,
            f"reauth_{entry.entry_id}",
            is_fixable=True,
            breaks_in_ha_version=None,
            severity=ir.IssueSeverity.ERROR,
            translation_key="reauth",
            translation_placeholders={"email": conf[CONF_EMAIL]},
        )
        raise ConfigEntryAuthFailed
    _LOGGER.debug("Authentication successful")
    melview = MelView(mv_auth, localcontrol=options.get(CONF_LOCAL))

    units = mv_auth.number_units()
    if units is False:
        _LOGGER.debug("Unable to determine number of devices")
        raise ConfigEntryNotReady("Unable to determine number of devices")
    if units == 0:
        _LOGGER.debug("Account has no devices")
        raise ConfigEntryError("Account has no devices")

    device_list = []
    _LOGGER.debug("Getting data")

    devices = await melview.async_get_devices_list()
    if devices is None:
        _LOGGER.debug("Unable to retrieve device list")
        raise ConfigEntryNotReady("Unable to retrieve device list")
    for device in devices:
        coordinator = MelViewCoordinator(hass, entry, device)
        await coordinator.async_config_entry_first_refresh()
        _LOGGER.debug("Device: " + device.get_friendly_name())
        device_list.append(coordinator)
    entry.runtime_data = device_list
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.debug("Set up coordinator(s): %s", entry.runtime_data)
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )

    return unload_ok


async def async_migrate_entry(hass, config_entry):
    """Migrate old config entry."""
    data = {**config_entry.data}
    options = {**config_entry.options}

    if CONF_LOCAL in data:
        options[CONF_LOCAL] = data.pop(CONF_LOCAL)
    if CONF_SENSOR in data:
        options[CONF_SENSOR] = data.pop(CONF_SENSOR)

    hass.config_entries.async_update_entry(config_entry, data=data, options=options)
    return True
