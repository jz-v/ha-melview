from __future__ import annotations

import logging

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

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
        | FanEntityFeature.SET_SPEED
    )

    def __init__(self, coordinator: MelViewCoordinator):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.get_id()}_lossnay"
        self._device = coordinator.device
        self._last_preset: str = "Lossnay"
        self._speed_codes = sorted(k for k in coordinator.fan if k != 0)
        _LOGGER.debug("Initialised Lossnay fan with speed codes: %s", self._speed_codes)

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
        elif percentage is not None:
            await self.async_set_percentage(percentage)
        else:
            if await self.coordinator.async_power_on():
                await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        if await self.coordinator.async_power_off():
            await self.coordinator.async_request_refresh()

    @property
    def percentage(self) -> int | None:
        code = self.coordinator.data.get("setfan")
        if code in self._speed_codes:
            percentage = ordered_list_item_to_percentage(self._speed_codes, code)
            _LOGGER.debug("Lossnay fan percentage: raw code=%s, calculated percentage=%s", code, percentage)
            return percentage
        _LOGGER.debug("Lossnay fan percentage: raw code=%s not in speed codes", code)
        return None

    @property
    def speed_count(self) -> int:
        count = len(self._speed_codes)
        _LOGGER.debug("Lossnay fan speed_count: speed_codes=%s, count=%d", self._speed_codes, count)
        return count

    async def async_set_percentage(self, percentage: int) -> None:
        code = percentage_to_ordered_list_item(self._speed_codes, percentage)
        _LOGGER.debug(
            "Lossnay fan set speed with percentage=%d, mapped code=%s",
            percentage,
            code
        )
        if await self.coordinator.async_set_speed_code(code):
            await self.coordinator.async_request_refresh()

    @property
    def device_info(self):
        """Create device"""
        return {
            "identifiers": {(DOMAIN, self._device.get_id())},
            "name": self._device.get_friendly_name(),
            "manufacturer": "Mitsubishi Electric",
            "model": self._device.model,
        }

async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up MelView Lossnay fans based on a config entry."""
    coordinators = entry.runtime_data
    entities = [
        MelViewLossnayFan(coordinator)
        for coordinator in coordinators
        if coordinator.device.get_unit_type() == "ERV"
    ]
    if entities:
        async_add_entities(entities, update_before_add=True)
