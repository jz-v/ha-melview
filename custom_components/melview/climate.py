import logging
from homeassistant.components.climate.const import (
    HVACMode,
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

_LOGGER = logging.getLogger(__name__)

DEPENDENCIES = []

HVAC_MODES = [HVACMode.AUTO, HVACMode.COOL, HVACMode.DRY, HVACMode.FAN_ONLY, HVACMode.HEAT, HVACMode.OFF]


# ---------------------------------------------------------------

class MelViewClimate(ClimateEntity):
    """Melview handler for Home Assistant"""
    def __init__(self, device, halfstep=False):
        self._enable_turn_on_off_backwards_compatibility = False
        self._device = device
        self._halfstep = halfstep

        self._name = device.get_friendly_name()
        self._unique_id = device.get_id()

        self._operations_list = [x for x in MODE] + [HVACMode.OFF]
        self._speeds_list = [x for x in self._device.fan_keyed]

        # Placeholders for state
        self._precision = PRECISION_WHOLE
        self._target_step = 1.0
        self._current_temp = None
        self._target_temp = None
        self._mode = HVACMode.OFF
        self._speed = None
        self._state = STATE_OFF


    async def async_added_to_hass(self):
        """Perform async operations when entity is added to hass."""
        self._precision = PRECISION_WHOLE
        self._target_step = 1.0
        if self._halfstep and await self._device.async_get_precision_halves():
            self._precision = PRECISION_HALVES
            self._target_step = 0.5

        await self._device.async_force_update()
        self._current_temp = await self._device.async_get_room_temperature()
        self._target_temp = await self._device.async_get_temperature()
        self._mode = await self._device.async_get_mode()
        self._speed = await self._device.async_get_speed()
        self._state = STATE_OFF
        if await self._device.async_is_power_on():
            self._state = self._mode

        self.async_write_ha_state()

    async def async_update(self):
        """Update device properties"""
        _LOGGER.debug('updating state')
        await self._device.async_force_update()

        self._precision = PRECISION_WHOLE
        self._target_step = 1.0
        if self._halfstep and await self._device.async_get_precision_halves():
            self._precision = PRECISION_HALVES
            self._target_step = 0.5

        self._current_temp = await self._device.async_get_room_temperature()
        self._target_temp = await self._device.async_get_temperature()

        self._mode = await self._device.async_get_mode()
        self._speed = await self._device.async_get_speed()

        self._state = self._mode
        
        if not await self._device.async_is_power_on():
            self._mode = 'off'
            self._state = STATE_OFF

    @property
    def name(self):
        """ Diplay name for HASS"""
        return self._name


    @property
    def unique_id(self):
        """ Get unique_id for HASS"""
        return self._unique_id


    @property
    def supported_features(self):
        """ Let HASS know feature support
            TODO: Handle looking at the device features?
        """
        return (ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF)


    @property
    def should_poll(self):
        """ Ensure HASS polls the unit"""
        return True


    @property
    def state(self):
        """Return the current state"""
        return self._state


    @property
    def is_on(self):
        """ Check unit is on"""
        return self._state != STATE_OFF


    @property
    def precision(self):
        """ Return the precision of the system"""
        return self._precision


    @property
    def temperature_unit(self):
        """ Define unit for temperature"""
        return UnitOfTemperature.CELSIUS


    @property
    def current_temperature(self):
        """ Get the current room temperature"""
        return self._current_temp


    @property
    def target_temperature(self):
        """ Get the target temperature"""
        return self._target_temp

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
        if self._mode in self._device.temp_ranges:
            return self._device.temp_ranges[self._mode]["min"]
        return super().min_temp

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature for the current HVAC mode."""
        if self._mode in self._device.temp_ranges:
            return self._device.temp_ranges[self._mode]["max"]
        return super().max_temp

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature"""
        return self._target_step


    @property
    def hvac_mode(self):
        """Get the current operating mode"""
        return self._mode


    @property
    def hvac_modes(self):
        """Get possible operating modes"""
        return self._operations_list


    @property
    def fan_mode(self):
        """Check the unit fan speed"""
        return self._speed


    @property
    def fan_modes(self):
        """Get the possible fan speeds"""
        return self._speeds_list

    async def async_set_temperature(self, **kwargs) -> None:
        """Set the target temperature"""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            _LOGGER.debug('setting temp %d', temp)
            if await self._device.async_set_temperature(temp):
                self._current_temp = temp
                self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode) -> None:
        """Set the fan speed"""
        speed = fan_mode
        _LOGGER.debug('set fan mode: %s', speed)
        if await self._device.async_set_speed(speed):
            self._speed = speed
            self._mode = await self._device.async_get_mode()
            self._state = self._mode
            self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode) -> None:
        _LOGGER.debug('set mode: %s', hvac_mode)
        if hvac_mode == 'off':
            await self.async_turn_off()
        elif await self._device.async_set_mode(hvac_mode):
            self._mode = hvac_mode
            self._state = hvac_mode
        self.async_write_ha_state()

    async def async_turn_on(self) ->None:
        """Turn on the unit"""
        _LOGGER.debug('power on')
        if await self._device.async_power_on():
            self._mode = await self._device.async_get_mode()
            self._state = self._mode
            self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Turn off the unit"""
        _LOGGER.debug('power off')
        if await self._device.async_power_off():
            self._mode = 'off'
            self._state = STATE_OFF
            self.async_write_ha_state()


# ---------------------------------------------------------------

async def async_setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the HASS component"""
    _LOGGER.debug('adding component')

    email = config[DOMAIN][CONF_EMAIL]
    password = config[DOMAIN][CONF_PASSWORD]
    local = config[DOMAIN][CONF_LOCAL]
    halfstep = config[DOMAIN][CONF_HALFSTEP]

    if email is None:
        _LOGGER.error('no email provided')
        return False

    if password is None:
        _LOGGER.error('no password provided')
        return False

    if local is None:
        _LOGGER.warning('local unspecified, defaulting to false')
        local = False

    if halfstep is None:
        _LOGGER.warning('halfstep unspecified, defaulting to false')
        halfstep = False

    mv_auth = MelViewAuthentication(email, password)
    result= await mv_auth.asynclogin()
    if not result:
        _LOGGER.error('login combination')
        return False

    melview = MelView(mv_auth, localcontrol=local)

    device_list = []

    devices = await melview.async_get_devices_list()
    for device in devices:
        await device.async_refresh()
        _LOGGER.debug('new device: %s', device.get_friendly_name())
        device_list.append(MelViewClimate(device, halfstep))

    add_devices(device_list)

    _LOGGER.debug('component successfully added')
    return True

async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up MelView device climate based on config_entry."""
    mel_devices = hass.data[DOMAIN][entry.entry_id]
    
    halfstep = entry.data.get(CONF_HALFSTEP, False)

    async_add_entities(
        [   
            MelViewClimate(mel_device, halfstep)
            for mel_device in mel_devices
        ],False
    )

 
# ---------------------------------------------------------------
