import logging
from homeassistant.components.climate.const import (
    HVACMode,
    HVACAction,
    ClimateEntityFeature
)
from homeassistant.components.climate import ClimateEntity
from homeassistant.const import (
    UnitOfTemperature,
    ATTR_TEMPERATURE,
    PRECISION_HALVES,
    PRECISION_WHOLE,
    STATE_OFF
)
from .melview import MelViewAuthentication, MelView, MODE
from .const import DOMAIN, CONF_EMAIL, CONF_PASSWORD, CONF_LOCAL, CONF_HALFSTEP
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .coordinator import MelViewCoordinator

_LOGGER = logging.getLogger(__name__)

DEPENDENCIES = []

HVAC_MODES = [HVACMode.AUTO, HVACMode.COOL, HVACMode.DRY, HVACMode.FAN_ONLY, HVACMode.HEAT, HVACMode.OFF]


class MelViewClimate(CoordinatorEntity, ClimateEntity):
    """MelView handler for Home Assistant"""
    def __init__(self, coordinator: MelViewCoordinator, halfstep: bool = False):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._device = coordinator.device
        device = coordinator.device

        self._enable_turn_on_off_backwards_compatibility = False
        self._halfstep = halfstep

        self._name = device.get_friendly_name()
        self._unique_id = device.get_id()

        self._operations_list = [x for x in MODE] + [HVACMode.OFF]
        self._speeds_list = [x for x in self._device.fan_keyed]

        # Placeholders for state
        self._precision = PRECISION_WHOLE
        self._target_step = 1.0

    async def async_added_to_hass(self):
        """Perform async operations when entity is added to hass."""
        await super().async_added_to_hass()
        self._precision = PRECISION_WHOLE
        self._target_step = 1.0
        if self._halfstep and await self._device.async_get_precision_halves():
            self._precision = PRECISION_HALVES
            self._target_step = 0.5

        await self._device.async_force_update()

    async def async_update(self):
        """Update device properties"""
        _LOGGER.debug('Update climate entity')
        await self._device.async_force_update()

        self._precision = PRECISION_WHOLE
        self._target_step = 1.0
        if self._halfstep and await self._device.async_get_precision_halves():
            self._precision = PRECISION_HALVES
            self._target_step = 0.5

    @property
    def name(self):
        """Diplay name for HASS"""
        return self._name

    @property
    def unique_id(self):
        """Get unique_id for HASS"""
        return self._unique_id

    @property
    def supported_features(self):
        """Let HASS know feature support"""
        return (ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF)

    @property
    def state(self):
        """Return the current state"""
        power = self.coordinator.data.get("power", 0)
        if power == 0:
            return STATE_OFF
        # Device is on—reflect its current HVAC mode
        return self.hvac_mode

    @property
    def is_on(self):
        """Check unit is on"""
        return self.state != STATE_OFF

    @property
    def precision(self):
        """Return the precision of the system"""
        return self._precision

    @property
    def temperature_unit(self):
        """Define unit for temperature"""
        return UnitOfTemperature.CELSIUS

    @property
    def current_temperature(self) -> float:
        """Get the current room temperature"""
        val = self.coordinator.data.get("roomtemp", 0)
        try:
            return float(val)
        except (TypeError, ValueError):
            _LOGGER.error("Invalid temperature value: %s", val)
            return 0.0

    @property
    def target_temperature(self) -> float | None:
        """Get the target temperature"""
        val = self.coordinator.data.get("settemp")
        try:
            return float(val)
        except (TypeError, ValueError):
            _LOGGER.error("Invalid target temperature value: %s", val)
            return None

    @property
    def device_info(self):
        """Create device"""
        return {
            "identifiers": {(DOMAIN, self._device.get_id())},
            "name": self._device.get_friendly_name(),
            "manufacturer": "Mitsubishi Electric",
            "model": self._device.model,
        }

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature for the current HVAC mode."""
        mode = self.hvac_mode
        if mode in self._device.temp_ranges:
            return self._device.temp_ranges[mode]["min"]
        return super().min_temp

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature for the current HVAC mode."""
        mode = self.hvac_mode
        if mode in self._device.temp_ranges:
            return self._device.temp_ranges[mode]["max"]
        return super().max_temp

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature"""
        return self._target_step

    @property
    def hvac_mode(self):
        """Get the current operating mode"""
        # If powered off, report OFF
        if self.coordinator.data.get("power", 0) == 0:
            return HVACMode.OFF
        mode_index = self.coordinator.data.get("setmode")
        try:
            return self._operations_list[mode_index]
        except (TypeError, IndexError):
            _LOGGER.error("Unknown mode index: %s", mode_index)
            return HVACMode.AUTO

    @property
    def hvac_modes(self):
        """Get possible operating modes"""
        return self._operations_list

    @property
    def fan_mode(self) -> str | None:
        """Return the current fan speed label."""
        code = self.coordinator.data.get("setfan")
        label = self._device.fan.get(code)
        if label is None:
            _LOGGER.error("Fan code %s not present in available modes", code)
        return label

    @property
    def fan_modes(self):
        """Get the possible fan speeds"""
        return self._speeds_list

    @property
    def hvac_action(self):
        """Get the current action."""
        if self.state == STATE_OFF:
            return HVACAction.OFF
        current = self.current_temperature
        target = self.target_temperature
        mode = self.hvac_mode
        if mode == HVACMode.COOL:
            if target is None or current is None:
                return None
            return HVACAction.IDLE if target > current else HVACAction.COOLING
        if mode == HVACMode.HEAT:
            if self._device._standby:
                return HVACAction.PREHEATING
            if target is None or current is None:
                return None
            return HVACAction.IDLE if target < current else HVACAction.HEATING
        if mode == HVACMode.DRY:
            return HVACAction.DRYING
        if mode == HVACMode.FAN_ONLY:
            return HVACAction.FAN
        return None

    async def async_set_temperature(self, **kwargs) -> None:
        """Set the target temperature"""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            _LOGGER.debug('Set temperature %d', temp)
            if await self._device.async_set_temperature(temp):
                await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode) -> None:
        """Set the fan speed"""
        speed = fan_mode
        _LOGGER.debug('Set fan: %s', speed)
        if await self._device.async_set_speed(speed):
            await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode) -> None:
        _LOGGER.debug('Set mode: %s', hvac_mode)
        if hvac_mode == 'off':
            await self.async_turn_off()
        elif await self._device.async_set_mode(hvac_mode):
            await self.coordinator.async_request_refresh()

    async def async_turn_on(self) ->None:
        """Turn on the unit"""
        _LOGGER.debug('Power on')
        if await self._device.async_power_on():
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn off the unit"""
        _LOGGER.debug('Power off')
        if await self._device.async_power_off():
            await self.coordinator.async_request_refresh()

async def async_setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the HASS component"""
    _LOGGER.debug('Adding component')

    email = config[DOMAIN][CONF_EMAIL]
    password = config[DOMAIN][CONF_PASSWORD]
    local = config[DOMAIN][CONF_LOCAL]
    halfstep = config[DOMAIN][CONF_HALFSTEP]

    if email is None:
        _LOGGER.error('No email provided')
        return False

    if password is None:
        _LOGGER.error('No password provided')
        return False

    if local is None:
        _LOGGER.warning('Var local unspecified, defaulting to false')
        local = False

    if halfstep is None:
        _LOGGER.warning('Var halfstep unspecified, defaulting to false')
        halfstep = False

    mv_auth = MelViewAuthentication(email, password)
    result= await mv_auth.asynclogin()
    if not result:
        _LOGGER.error('Login combination')
        return False

    melview = MelView(mv_auth, localcontrol=local)

    device_list = []

    devices = await melview.async_get_devices_list()
    for device in devices:
        await device.async_refresh()
        _LOGGER.debug('New device: %s', device.get_friendly_name())
        device_list.append(MelViewClimate(device, halfstep))

    add_devices(device_list)

    _LOGGER.debug('Component successfully added')
    return True

async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up MelView device climate based on config_entry."""
    coordinators = hass.data[DOMAIN][entry.entry_id]
    halfstep = entry.data.get(CONF_HALFSTEP, False)
    entities = [
        MelViewClimate(coordinator, halfstep)
        for coordinator in coordinators
    ]
    async_add_entities(entities, update_before_add=True)