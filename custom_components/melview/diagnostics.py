"""Diagnostics support for MelView."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from . import MelViewConfigEntry
from .const import DOMAIN
from .coordinator import MelViewCoordinator

# The entry title and unique ID are the account email; "id" is the unit ID
TO_REDACT = {CONF_EMAIL, CONF_PASSWORD, "title", "unique_id", "id", "localip"}


def _unit_diagnostics(coordinator: MelViewCoordinator) -> dict[str, Any]:
    """Return what MelView reported for a unit and how it was interpreted."""
    device = coordinator.device
    return {
        "name": device.get_friendly_name(),
        "capabilities": device._caps,
        "data": coordinator.data,
        "fan_speeds": device.fan,
        "temperature_ranges": device.temp_ranges,
        # With local commands on, _localip holds the IP once capabilities provide it
        "local_ip_found": isinstance(device._localip, str),
        "last_update_success": coordinator.last_update_success,
        "last_error": (
            str(coordinator.last_exception) if coordinator.last_exception else None
        ),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MelViewConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinators = entry.runtime_data
    return async_redact_data(
        {
            "entry": entry.as_dict(),
            "account": {
                "units_reported": coordinators[0].device._authentication.number_units(),
                "units_set_up": len(coordinators),
            },
            "units": [_unit_diagnostics(coordinator) for coordinator in coordinators],
        },
        TO_REDACT,
    )


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: MelViewConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Return diagnostics for one unit."""
    unit_ids = {
        identifier for domain, identifier in device.identifiers if domain == DOMAIN
    }
    coordinator = next(
        coordinator
        for coordinator in entry.runtime_data
        if str(coordinator.device.get_id()) in unit_ids
    )
    return async_redact_data(
        {"entry": entry.as_dict(), "unit": _unit_diagnostics(coordinator)},
        TO_REDACT,
    )
