from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_SENSOR
from .entity import MelViewBaseEntity

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

    coordinators = entry.runtime_data

    entities = [MelViewCurrentTempSensor(coordinator) for coordinator in coordinators]
    for coordinator in coordinators:
        if coordinator.device.get_unit_type() == "ERV":
            entities.extend(
                [
                    MelViewOutdoorTempSensor(coordinator),
                    MelViewSupplyTempSensor(coordinator),
                    MelViewExhaustTempSensor(coordinator),
                    MelViewCoreEfficiencySensor(coordinator),
                ]
            )
    async_add_entities(entities, update_before_add=True)


class MelViewCurrentTempSensor(MelViewBaseEntity, SensorEntity):
    """Sensor representing the current room temperature for a MelView device."""

    _attr_has_entity_name = True
    _attr_name = "Current Temperature"

    def __init__(self, coordinator):
        """Initialize sensor, tied to a DataUpdateCoordinator."""
        super().__init__(coordinator, coordinator.device)
        api = coordinator.device
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_unique_id = f"{api.get_id()}_current_temp"
        self._attr_extra_state_attributes = {"source": "melview.py cache"}

    @property
    def native_value(self):
        """Return the current room temperature from cached data."""
        data = self.coordinator.data or {}
        return float(data.get("roomtemp", 0))


class MelViewOutdoorTempSensor(MelViewBaseEntity, SensorEntity):
    """Sensor representing the outdoor (fresh air) temperature."""

    _attr_has_entity_name = True
    _attr_name = "Fresh Air"

    def __init__(self, coordinator):
        super().__init__(coordinator, coordinator.device)
        api = coordinator.device
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_unique_id = f"{api.get_id()}_outdoor_temp"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        return float(data.get("outdoortemp", 0))


class MelViewSupplyTempSensor(MelViewBaseEntity, SensorEntity):
    """Sensor for the pre-warmed supply air temperature."""

    _attr_has_entity_name = True
    _attr_name = "Pre-warmed"

    def __init__(self, coordinator):
        super().__init__(coordinator, coordinator.device)
        api = coordinator.device
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_unique_id = f"{api.get_id()}_supply_temp"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        room = float(data.get("roomtemp", 0))
        outdoor = float(data.get("outdoortemp", 0))
        efficiency = float(data.get("coreefficiency", 0))
        return round(outdoor + efficiency * (room - outdoor), 1)


class MelViewExhaustTempSensor(MelViewBaseEntity, SensorEntity):
    """Sensor for the stale air temperature leaving the unit."""

    _attr_has_entity_name = True
    _attr_name = "Stale Air"

    def __init__(self, coordinator):
        super().__init__(coordinator, coordinator.device)
        api = coordinator.device
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_unique_id = f"{api.get_id()}_exhaust_temp"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        return float(data.get("exhausttemp", 0))


class MelViewCoreEfficiencySensor(MelViewBaseEntity, SensorEntity):
    """Sensor for the core heat recovery efficiency percentage."""

    _attr_has_entity_name = True
    _attr_name = "Core Efficiency"

    def __init__(self, coordinator):
        super().__init__(coordinator, coordinator.device)
        api = coordinator.device
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_unique_id = f"{api.get_id()}_core_efficiency"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        return round(float(data.get("coreefficiency", 0)) * 100, 1)
