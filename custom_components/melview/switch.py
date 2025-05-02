import logging
from .melview import MelViewAuthentication, MelView
from homeassistant.components.switch import SwitchEntity

_LOGGER = logging.getLogger(__name__)
DOMAIN = 'melview'
# REQUIREMENTS = ['requests']
DEPENDENCIES = []

class MelViewZoneSwitch(SwitchEntity):
    """Melview zone switch handler for Home Assistant"""
    def __init__(self, zone, parentClimate):
        self._id = zone.id
        self._name = zone.name
        self._status = zone.status
        self._climate = parentClimate

    async def async_update(self):
        await self._climate.async_force_update()
        zone = self._climate.get_zone(self._id)
        self._name = zone.name
        self._status = zone.status

    @property
    def name(self):
        """ Diplay name for HASS
        """
        return f"Zone {self._name}"

    @property
    def unique_id(self):
        """ Get unique_id for HASS
        """
        return f"{self._climate.get_id()}-{self._id}"

    @property
    def should_poll(self):
        """ Ensure HASS polls the zone"""
        return True

    @property
    def is_on(self):
        """ Check zone is on"""
        return self._status == 1
    
    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._climate.get_id())},
        }

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._climate.get_id())},
        }

    async def async_turn_on(self):
        """ Turn on the zone"""
        _LOGGER.debug('power on zone')
        if await self._climate.async_enable_zone(self._id):
            self._status = 1

    async def async_turn_off(self):
        """ Turn off the zone"""
        _LOGGER.debug('power off zone')
        if await self._climate.async_disable_zone(self._id):
            self._status = 0

async def async_setup_entry(
    hass, entry, async_add_entities
) -> None:
    """Set up Melview device climate based on config_entry."""
    mel_devices = hass.data[DOMAIN][entry.entry_id]
    
    async_add_entities(
        [   
            MelViewZoneSwitch(zone,mel_device)
            for mel_device in mel_devices
            for zone in mel_device.get_zones()
        ],False
    )