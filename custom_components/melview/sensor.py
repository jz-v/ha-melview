from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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

    entities = [MelviewCurrentTempSensor(coordinator) for coordinator in devices]
    async_add_entities(entities, update_before_add=True)


class MelviewCurrentTempSensor(CoordinatorEntity, SensorEntity):
    """Sensor representing the current room temperature for a Melview device."""

    def __init__(self, coordinator):
        """Initialize sensor, tied to a DataUpdateCoordinator."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        api = coordinator.device
        self._attr_name = f"{api.get_friendly_name()} Current Temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_unique_id = f"{api.get_id()}_current_temp"
        self._attr_extra_state_attributes = {"source": "melview.py cache"}

    @property
    def native_value(self):
        """Return the current room temperature from cached data."""
        data = self.coordinator.data or {}
        return float(data.get("roomtemp", 0))
    
    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.device.get_id())},
        }