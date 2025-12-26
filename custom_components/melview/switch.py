import logging
from homeassistant.components.switch import SwitchEntity

from .coordinator import MelViewCoordinator
from .entity import MelViewBaseEntity

_LOGGER = logging.getLogger(__name__)


class MelViewZoneSwitch(MelViewBaseEntity, SwitchEntity):
    """MelView zone switch handler for Home Assistant"""

    def __init__(self, coordinator: MelViewCoordinator, zone):
        super().__init__(coordinator, coordinator.device)
        self._id = zone.id
        self._attr_unique_id = f"{self.coordinator.get_id()}-{self._id}"
        self._attr_name = f"Zone {zone.name}"

    @property
    def is_on(self) -> bool:
        """Check if the zone is currently on."""
        zone = self.coordinator.get_zone(self._id)
        return bool(zone.status)

    @property
    def extra_state_attributes(self):
        """Return spill status as attribute."""
        zone = self.coordinator.get_zone(self._id)
        return {
            "Spill active": zone.status == 2,
        }

    async def async_turn_on(self):
        """Turn on the zone"""
        _LOGGER.debug("Switch on zone %s", self._attr_name)
        if await self.coordinator.async_enable_zone(self._id):
            await self.coordinator.async_refresh()

    async def async_turn_off(self):
        """Turn off the zone"""
        _LOGGER.debug("Switch off zone %s", self._attr_name)
        if await self.coordinator.async_disable_zone(self._id):
            await self.coordinator.async_refresh()


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up MelView device climate based on config_entry."""
    coordinators = entry.runtime_data

    entities = [
        MelViewZoneSwitch(coordinator, zone)
        for coordinator in coordinators
        for zone in coordinator.get_zones()
    ]

    async_add_entities(entities, update_before_add=True)
