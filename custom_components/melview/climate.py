"""Climate entities for MelView air conditioners."""

import logging

from homeassistant.components import logbook
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    PRECISION_HALVES,
    PRECISION_WHOLE,
    UnitOfTemperature,
)

from .const import REPORT_ISSUE_URL
from .coordinator import MelViewCoordinator
from .entity import MelViewBaseEntity
from .melview import MODE

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


class MelViewClimate(MelViewBaseEntity, ClimateEntity):
    """MelView handler for Home Assistant."""

    _attr_name = None

    def __init__(self, coordinator: MelViewCoordinator):
        """Initialize the climate entity for a unit."""
        super().__init__(coordinator, coordinator.device)
        self._device = coordinator.device
        device = coordinator.device

        self._attr_unique_id = device.get_id()

        self._operations_list = [*self._device.modes, HVACMode.OFF]
        self._speeds_list = list(self._device.fan_keyed)
        # Fan codes already warned about, so each is logged once
        self._unknown_fan_codes: set = set()

        self._precision = PRECISION_WHOLE
        self._target_step = 1.0

    async def async_added_to_hass(self):
        """Perform async operations when entity is added to hass."""
        await super().async_added_to_hass()
        self._precision = PRECISION_WHOLE
        self._target_step = 1.0
        if getattr(self._device, "halfdeg", False):
            self._precision = PRECISION_HALVES
            self._target_step = 0.5

    @property
    def supported_features(self):
        """Let HASS know feature support."""
        features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        if self._device.fan:
            features |= ClimateEntityFeature.FAN_MODE
        if self._set_mode in (
            HVACMode.AUTO,
            HVACMode.HEAT,
            HVACMode.COOL,
            HVACMode.DRY,
        ):
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
        return features

    @property
    def precision(self):
        """Return the precision of the system."""
        return self._precision

    @property
    def native_temperature_unit(self) -> str:
        """Return the unit temperatures are reported in."""
        return UnitOfTemperature.CELSIUS

    @property
    def native_current_temperature(self) -> float | None:
        """Get the current room temperature."""
        return self._data_float("roomtemp")

    @property
    def native_target_temperature(self) -> float | None:
        """Get the target temperature."""
        return self._data_float("settemp")

    # Home Assistant before 2026.11 reads these names instead of the native_
    # ones above. Remove them once the minimum version in hacs.json is 2026.11
    # or newer; Home Assistant 2027.11 stops supporting them.
    @property
    def temperature_unit(self) -> str:
        """Return the unit temperatures are reported in."""
        return self.native_temperature_unit

    @property
    def current_temperature(self) -> float | None:
        """Get the current room temperature."""
        return self.native_current_temperature

    @property
    def target_temperature(self) -> float | None:
        """Get the target temperature."""
        return self.native_target_temperature

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature for the current HVAC mode."""
        mode = self._set_mode
        if mode in self._device.temp_ranges:
            return self._device.temp_ranges[mode]["min"]
        return super().min_temp

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature for the current HVAC mode."""
        mode = self._set_mode
        if mode in self._device.temp_ranges:
            return self._device.temp_ranges[mode]["max"]
        return super().max_temp

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return self._target_step

    @property
    def _set_mode(self) -> HVACMode:
        """Get the configured mode, which the unit reports even when off."""
        mode_index = self.coordinator.data.get("setmode")
        return next(
            (mode for mode, val in MODE.items() if val == mode_index), HVACMode.AUTO
        )

    @property
    def hvac_mode(self):
        """Get the current operating mode."""
        if self.coordinator.data.get("power", 0) == 0:
            return HVACMode.OFF
        return self._set_mode

    @property
    def hvac_modes(self):
        """Get possible operating modes."""
        return self._operations_list

    @property
    def fan_mode(self) -> str | None:
        """Return the current fan speed label."""
        code = self.coordinator.data.get("setfan")
        label = self._device.fan.get(code)
        if label is None and code is not None and code not in self._unknown_fan_codes:
            self._unknown_fan_codes.add(code)
            _LOGGER.warning(
                "Unit %s reported fan speed code %s, which is not one of its "
                "known speeds. Please raise an issue with a diagnostics "
                "download attached: %s",
                self._device.get_friendly_name(),
                code,
                REPORT_ISSUE_URL,
            )
        return label

    @property
    def fan_modes(self):
        """Get the possible fan speeds."""
        return self._speeds_list

    @property
    def hvac_action(self):
        """Get the current action, returns None unless explicitly known."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if self.hvac_mode == HVACMode.HEAT:
            if self.coordinator.data.get("standby"):
                return HVACAction.PREHEATING
            return None
        if self.hvac_mode == HVACMode.FAN_ONLY:
            return HVACAction.FAN
        return None

    async def async_set_temperature(self, **kwargs) -> None:
        """Set the target temperature, and the operating mode if given."""
        # Set mode first so the temperature is checked against its range
        if (hvac_mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            await self.async_set_hvac_mode(hvac_mode)
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            _LOGGER.debug("Set temperature %.1f", temp)
            await self._async_command(self._device.async_set_temperature(temp))
            await self.coordinator.async_refresh()

    async def async_set_fan_mode(self, fan_mode) -> None:
        """Set the fan speed."""
        speed = fan_mode
        _LOGGER.debug("Set fan: %s", speed)
        await self._async_command(self._device.async_set_speed(speed))
        await self.coordinator.async_refresh()
        parsed_speed = fan_mode.title()
        logbook.log_entry(
            hass=self.hass,
            name=self.name,
            message=f"Fan speed set to {parsed_speed}",
            entity_id=self.entity_id,
        )

    async def async_set_hvac_mode(self, hvac_mode) -> None:
        """Set the operating mode, turning the unit off for HVACMode.OFF."""
        _LOGGER.debug("Set mode: %s", hvac_mode)
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            return
        await self._async_command(self._device.async_set_mode(hvac_mode))
        await self.coordinator.async_refresh()

    async def async_turn_on(self) -> None:
        """Turn on the unit."""
        _LOGGER.debug("Power on")
        await self._async_command(self._device.async_power_on())
        await self.coordinator.async_refresh()

    async def async_turn_off(self) -> None:
        """Turn off the unit."""
        _LOGGER.debug("Power off")
        await self._async_command(self._device.async_power_off())
        await self.coordinator.async_refresh()


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up MelView device climate based on config_entry."""
    coordinators = entry.runtime_data.coordinators
    entities = [
        MelViewClimate(coordinator)
        for coordinator in coordinators
        if coordinator.device.get_unit_type() != "ERV"
    ]
    async_add_entities(entities)
