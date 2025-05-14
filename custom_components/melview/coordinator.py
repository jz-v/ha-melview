import asyncio
from datetime import timedelta
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .melview import MelViewDevice

import logging

_LOGGER = logging.getLogger(__name__)

class MelViewCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch data from a Melview API once per interval."""

    def __init__(self, hass, config_entry, device: MelViewDevice):
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"melview: {device.get_friendly_name()}",
            config_entry=config_entry,
            update_interval=timedelta(seconds=30),
            always_update=True,
        )
        self.device = device
        self._caps: dict | None = None
    
    def __getattr__(self, name: str):
        """Forward any missing attribute lookups to the underlying MelViewDevice."""
        return getattr(self.device, name)

    # async def _async_setup(self):
    #     """Set up the coordinator."""
    #     self._device_info = await self.async_refresh_device_caps()
    #     self._device = await self.api._async_update_data()

    async def _async_update_data(self):
        """Fetch data from the melview API."""
        try:
            # On first run, cache static capabilities
            if self._caps is None:
                self._caps = await self.device.async_refresh_device_caps()

            # Single API call
            ok = await self.device.async_refresh_device_info()
            if not ok or self.device._json is None:
                raise UpdateFailed("Failed to refresh melview info")

            return self.device._json

        except Exception as err:
            raise UpdateFailed(f"Error fetching melview data: {err}") from err