from __future__ import annotations

import logging

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MelViewCoordinator
from .melview import LOSSNAY_PRESETS

_LOGGER = logging.getLogger(__name__)


class MelViewLossnayFan(CoordinatorEntity, FanEntity):
    """Fan entity to control Lossnay ERV units."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_preset_modes = list(LOSSNAY_PRESETS)
    _attr_supported_features = (
        FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
        | FanEntityFeature.PRESET_MODE
    )

    def __init__(self, coordinator: MelViewCoordinator):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.get_id()}_lossnay"
        self._last_preset: str = "Lossnay"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.get("power") == 1

    @property
    def preset_mode(self) -> str | None:
        code = self.coordinator.data.get("setmode")
        return next((name for name, val in LOSSNAY_PRESETS.items() if val == code), None)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode not in LOSSNAY_PRESETS:
            _LOGGER.error("Preset mode %s not supported", preset_mode)
            return
        if not self.is_on:
            if not await self.coordinator.async_power_on():
                return
        if await self.coordinator.async_set_lossnay_preset(preset_mode):
            self._last_preset = preset_mode
            await self.coordinator.async_request_refresh()

    async def async_turn_on(
        self,
        preset_mode: str | None = None,
        percentage: int | None = None,
        **kwargs,
    ) -> None:
        if preset_mode:
            await self.async_set_preset_mode(preset_mode)
        else:
            if await self.coordinator.async_power_on():
                await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        if await self.coordinator.async_power_off():
            await self.coordinator.async_request_refresh()

    @property
    def device_info(self):
        return {"identifiers": {(DOMAIN, self.coordinator.get_id())}}


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up MelView Lossnay fans based on a config entry."""
    coordinators = hass.data[DOMAIN][entry.entry_id]
    entities = [
        MelViewLossnayFan(coordinator)
        for coordinator in coordinators
        if coordinator.device.get_unit_type() == "ERV"
    ]
    if entities:
        async_add_entities(entities, update_before_add=True)
