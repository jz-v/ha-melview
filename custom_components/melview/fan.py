"""Fan entities for MelView Lossnay ERV units."""

from __future__ import annotations

import logging

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from .coordinator import MelViewCoordinator
from .entity import MelViewBaseEntity
from .melview import LOSSNAY_PRESETS

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


class MelViewLossnayFan(MelViewBaseEntity, FanEntity):
    """Fan entity to control Lossnay ERV units."""

    _attr_name = None
    _attr_supported_features = (
        FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
        | FanEntityFeature.PRESET_MODE
        | FanEntityFeature.SET_SPEED
    )

    def __init__(self, coordinator: MelViewCoordinator):
        """Initialize the fan entity for a Lossnay unit."""
        super().__init__(coordinator, coordinator.device)
        self._attr_unique_id = f"{coordinator.get_id()}_lossnay"
        self._attr_preset_modes = list(LOSSNAY_PRESETS)
        self._device = coordinator.device
        self._speed_codes = sorted(k for k in coordinator.fan if k != 0)
        _LOGGER.debug("Initialised Lossnay fan with speed codes: %s", self._speed_codes)

    @property
    def is_on(self) -> bool:
        """Return whether the unit is on."""
        return self.coordinator.data.get("power") == 1

    @property
    def preset_mode(self) -> str | None:
        """Return the current Lossnay preset, if it is a known one."""
        code = self.coordinator.data.get("setmode")
        return next(
            (name for name, val in LOSSNAY_PRESETS.items() if val == code), None
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        # Home Assistant has already checked preset_mode is in preset_modes
        """Set the Lossnay preset, turning the unit on first if needed."""
        if not self.is_on:
            await self._async_command(self.coordinator.async_power_on())
        await self._async_command(
            self.coordinator.async_set_lossnay_preset(preset_mode)
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs,
    ) -> None:
        """Turn the unit on, optionally with a preset or speed."""
        if preset_mode:
            await self.async_set_preset_mode(preset_mode)
        elif percentage is not None:
            await self.async_set_percentage(percentage)
        else:
            await self._async_command(self.coordinator.async_power_on())
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the unit off."""
        await self._async_command(self.coordinator.async_power_off())
        await self.coordinator.async_request_refresh()

    @property
    def percentage(self) -> int | None:
        """Return the fan speed as a percentage of the available speeds."""
        code = self.coordinator.data.get("setfan")
        if code in self._speed_codes:
            percentage = ordered_list_item_to_percentage(self._speed_codes, code)
            _LOGGER.debug(
                "Lossnay fan percentage: raw code=%s, calculated percentage=%s",
                code,
                percentage,
            )
            return percentage
        _LOGGER.debug("Lossnay fan percentage: raw code=%s not in speed codes", code)
        return None

    @property
    def speed_count(self) -> int:
        """Return the number of fan speeds."""
        count = len(self._speed_codes)
        _LOGGER.debug(
            "Lossnay fan speed_count: speed_codes=%s, count=%d",
            self._speed_codes,
            count,
        )
        return count

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the fan speed from a percentage."""
        code = percentage_to_ordered_list_item(self._speed_codes, percentage)
        _LOGGER.debug(
            "Lossnay fan set speed with percentage=%d, mapped code=%s", percentage, code
        )
        await self._async_command(self.coordinator.async_set_speed_code(code))
        await self.coordinator.async_request_refresh()


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up MelView Lossnay fans based on a config entry."""
    coordinators = entry.runtime_data
    entities = [
        MelViewLossnayFan(coordinator)
        for coordinator in coordinators
        if coordinator.device.get_unit_type() == "ERV"
    ]
    if entities:
        async_add_entities(entities)
