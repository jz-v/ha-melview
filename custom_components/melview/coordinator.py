import json
from datetime import timedelta
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
            name=f"MelView: {device.get_friendly_name()}",
            config_entry=config_entry,
            update_interval=timedelta(seconds=30),
            always_update=True,
        )
        self.device = device
        self._caps: dict | None = None

    def __getattr__(self, name: str):
        """Forward any missing attribute lookups to the underlying MelViewDevice."""
        return getattr(self.device, name)

    async def _async_update_data(self):
        """Fetch data from the MelView API."""
        try:
            if self._caps is None:
                self._caps = await self.device.async_refresh_device_caps()
                _LOGGER.debug(
                    "Unit capabilities: %s", json.dumps(self.device._caps, indent=2)
                )
            ok = await self.device.async_refresh_device_info()
            if not ok or self.device._json is None:
                raise UpdateFailed("Failed to refresh MelView info")
            _LOGGER.debug("Data: %s", json.dumps(self.device._json, indent=2))
            return self.device._json
        except Exception as err:
            raise UpdateFailed(str(err)) from err