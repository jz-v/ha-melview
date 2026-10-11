"""Tests for the MelView device client.

Home Assistant validates action input before it reaches the integration, so
these call the device directly to check its own input checks.
"""

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.melview.melview import MelViewDevice, MelViewValidationError

from .conftest import MelViewApi


@pytest.fixture
def device(init_integration: MockConfigEntry) -> MelViewDevice:
    """Return the set-up MelView device."""
    return init_integration.runtime_data[0].device


@pytest.mark.parametrize(
    ("method", "value", "message"),
    [
        ("async_set_speed", "turbo", "Fan speed turbo not supported"),
        ("async_set_speed_code", 9, "Fan speed code 9 not supported"),
        ("async_set_mode", "heat_cool", "Mode heat_cool not supported"),
        ("async_set_lossnay_preset", "Boost", "Unknown Lossnay preset Boost"),
    ],
)
async def test_invalid_input_rejected_before_sending(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    device: MelViewDevice,
    method: str,
    value: str | int,
    message: str,
) -> None:
    """Invalid input raises without turning the unit on or sending anything."""
    melview_api.unit["power"] = 0
    await device.async_refresh_device_info()

    with pytest.raises(MelViewValidationError, match=message):
        await getattr(device, method)(value)
    assert melview_api.commands == []


async def test_unknown_mode_treated_as_auto(
    hass: HomeAssistant, melview_api: MelViewApi, device: MelViewDevice
) -> None:
    """A mode code the integration does not know is treated as auto."""
    melview_api.unit["setmode"] = 5
    await device.async_refresh_device_info()

    assert await device.async_get_mode() == HVACMode.AUTO
