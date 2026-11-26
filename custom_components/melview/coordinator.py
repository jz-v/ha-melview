"""Data update coordinator for MelView units."""

from dataclasses import dataclass
from datetime import timedelta
import json
import logging

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .melview import MelViewAuthError, MelViewDevice

_LOGGER = logging.getLogger(__name__)


class MelViewCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch data from a MelView API once per interval."""

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

    def __getattr__(self, name: str):
        """Forward any missing attribute lookups to the underlying MelViewDevice."""
        return getattr(self.device, name)

    async def _async_update_data(self):
        """Fetch data from the MelView API."""
        try:
            data = await self.device.async_refresh_device_info()
        except MelViewAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except Exception as err:
            raise UpdateFailed(str(err)) from err
        _LOGGER.debug("Data: %s", json.dumps(data, indent=2))
        return data


@dataclass
class MelViewData:
    """The units of a MelView account."""

    coordinators: list[MelViewCoordinator]
    # Units that did not respond at setup, polled until they do and then added
    not_responding: list[MelViewCoordinator]
