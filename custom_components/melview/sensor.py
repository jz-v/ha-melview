from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.entity import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_SENSOR

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MelView temperature sensors from a config entry."""
    if not entry.options.get(CONF_SENSOR, True):
        _LOGGER.debug("Sensor option is disabled in config entry.")
        return

    devices = hass.data[DOMAIN][entry.entry_id]

    entities = [MelviewCurrentTempSensor(device) for device in devices]
    async_add_entities(entities, update_before_add=True)


class MelviewCurrentTempSensor(SensorEntity):
    """Sensor representing the current room temperature for a Melview device."""

    def __init__(self, device):
        self._device = device
        self._attr_name = f"{device.get_friendly_name()} Current Temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_entity_category = None
        self._attr_should_poll = True
        self._attr_unique_id = f"{device._deviceid}_current_temp"
        self._attr_extra_state_attributes = {"source": "melview.py cache"}
        self._current_temp = None

    async def async_added_to_hass(self):
        self._current_temp = await self._device.async_get_room_temperature()
        self.async_write_ha_state()

    async def async_update(self):
        """Fetch updated data from the device."""
        await self._device.async_refresh_device_info()
        self._current_temp = await self._device.async_get_room_temperature()

    @property
    def native_value(self):
        """Return the averaged room temperature."""
        return self._current_temp
    
    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device.get_id())},
        }