from __future__ import annotations
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import MelViewCoordinator

class MelViewBaseEntity(CoordinatorEntity[MelViewCoordinator]):
    """Shared base for all MelView entities."""
    _attr_has_entity_name = True

    def __init__(self, coordinator: MelViewCoordinator, device) -> None:
        super().__init__(coordinator)
        self._device = device
        self._attr_device_info = DeviceInfo(
            identifiers = {(DOMAIN, device.get_id())},
            name = device.get_friendly_name(),
            manufacturer = MANUFACTURER,
            model = getattr(device, "model", None),
        )