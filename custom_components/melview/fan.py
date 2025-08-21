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

_LOGGER = logging.getLogger(__name__)

LOSSNAY_PRESETS = {
    "Lossnay": "MD1",
    "Bypass": "MD7",
    "Auto Lossnay": "MD3",
}

PRESET_BY_CODE = {1: "Lossnay", 7: "Bypass", 3: "Auto Lossnay"}


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
        self._last_preset: str = "Lossnay"
        self._speed_codes = sorted(k for k in coordinator.fan if k != 0)

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.get("power") == 1

    @property
    def preset_mode(self) -> str | None:
        code = self.coordinator.data.get("setmode")
        return PRESET_BY_CODE.get(code)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode not in LOSSNAY_PRESETS:
            _LOGGER.error("Preset mode %s not supported", preset_mode)
            return
        if not self.is_on:
            if not await self.coordinator.async_power_on():
                return
        command = LOSSNAY_PRESETS[preset_mode]
        if await self.coordinator.async_send_command(command):
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
            return ordered_list_item_to_percentage(self._speed_codes, code)
        return None

    @property
    def speed_count(self) -> int:
        return len(self._speed_codes)

    async def async_set_percentage(self, percentage: int) -> None:
        code = percentage_to_ordered_list_item(self._speed_codes, percentage)
        label = self.coordinator.fan.get(code)
        if label and await self.coordinator.async_set_speed(label):
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
