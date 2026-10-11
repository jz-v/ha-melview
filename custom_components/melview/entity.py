from __future__ import annotations

from collections.abc import Awaitable

from aiohttp import ClientError
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import MelViewCoordinator
from .melview import MelViewAuthError, MelViewError, MelViewValidationError


class MelViewBaseEntity(CoordinatorEntity[MelViewCoordinator]):
    """Shared base for all MelView entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MelViewCoordinator, device) -> None:
        super().__init__(coordinator)
        self._device = device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.get_id())},
            name=device.get_friendly_name(),
            manufacturer=MANUFACTURER,
            model=getattr(device, "model", None),
        )

    async def _async_command(self, command: Awaitable[None]) -> None:
        """Await a device command, raising Home Assistant errors on failure."""
        try:
            await command
        except MelViewValidationError as err:
            raise ServiceValidationError(str(err)) from err
        except MelViewAuthError as err:
            self.coordinator.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(str(err)) from err
        except (MelViewError, ConnectionError, ClientError, TimeoutError) as err:
            raise HomeAssistantError(
                f"MelView command failed for {self._device.get_friendly_name()}: {err}"
            ) from err
