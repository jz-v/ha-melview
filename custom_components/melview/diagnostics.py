"""Diagnostics support for MelView."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from . import MelViewConfigEntry
from .const import DOMAIN
from .coordinator import MelViewCoordinator


def _entry_diagnostics(entry: MelViewConfigEntry) -> dict[str, Any]:
    """Return the config entry without the email and password.

    The entry title and unique ID are the email too, so they are left out.
    """
    entry_dict = entry.as_dict()
    del entry_dict["title"], entry_dict["unique_id"]
    entry_dict["data"] = {
        key: value
        for key, value in entry.data.items()
        if key not in (CONF_EMAIL, CONF_PASSWORD)
    }
    return entry_dict


def _without_zone_names(unit_data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a copy of unit data without zone names, which can be people's names."""
    if unit_data is None or "zones" not in unit_data:
        return unit_data
    return {
        **unit_data,
        "zones": [
            {key: value for key, value in zone.items() if key != "name"}
            for zone in unit_data["zones"]
        ],
    }


def _unit_diagnostics(coordinator: MelViewCoordinator) -> dict[str, Any]:
    """Return what MelView reported for a unit and how it was interpreted."""
    device = coordinator.device
    return {
        "name": device.get_friendly_name(),
        "capabilities": _without_zone_names(device.capabilities),
        "data": _without_zone_names(coordinator.data),
        "fan_speeds": device.fan,
        "temperature_ranges": device.temp_ranges,
        "last_update_success": coordinator.last_update_success,
        "last_error": (
            str(coordinator.last_exception) if coordinator.last_exception else None
        ),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MelViewConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data
    return {
        "entry": _entry_diagnostics(entry),
        "account": {
            "units_reported": data.coordinators[0].device.authentication.number_units(),
            "units_set_up": len(data.coordinators),
        },
        "units": [_unit_diagnostics(coordinator) for coordinator in data.coordinators],
        "units_not_responding": [
            _unit_diagnostics(coordinator) for coordinator in data.not_responding
        ],
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: MelViewConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Return diagnostics for one unit.

    The unit can be one that did not respond at setup, or one no longer in
    the account whose device has not been cleaned up yet (unit is None).
    """
    data = entry.runtime_data
    unit_ids = {
        identifier for domain, identifier in device.identifiers if domain == DOMAIN
    }
    coordinator = next(
        (
            coordinator
            for coordinator in (*data.coordinators, *data.not_responding)
            if str(coordinator.device.get_id()) in unit_ids
        ),
        None,
    )
    return {
        "entry": _entry_diagnostics(entry),
        "unit": _unit_diagnostics(coordinator) if coordinator else None,
        "set_up": coordinator in data.coordinators,
    }
