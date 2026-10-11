"""Tests for the MelView Lossnay fan."""

from typing import Any

import pytest
from homeassistant.components.fan import (
    ATTR_PERCENTAGE,
    ATTR_PERCENTAGE_STEP,
    ATTR_PRESET_MODE,
    ATTR_PRESET_MODES,
    SERVICE_SET_PERCENTAGE,
    SERVICE_SET_PRESET_MODE,
)
from homeassistant.components.fan import (
    DOMAIN as FAN_DOMAIN,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import MelViewApi, setup_entry

FAN = "fan.lossnay"


async def call(hass: HomeAssistant, service: str, **data: Any) -> None:
    """Call a fan action on the test entity."""
    await hass.services.async_call(
        FAN_DOMAIN, service, {ATTR_ENTITY_ID: FAN, **data}, blocking=True
    )


@pytest.fixture
async def lossnay(
    hass: HomeAssistant, erv_api: MelViewApi, config_entry: MockConfigEntry
) -> MelViewApi:
    """Set up the integration with a Lossnay unit."""
    await setup_entry(hass, config_entry)
    return erv_api


async def test_state(hass: HomeAssistant, lossnay: MelViewApi) -> None:
    """The fan shows power, preset and speed."""
    state = hass.states.get(FAN)

    assert state.state == STATE_ON
    assert state.attributes[ATTR_PRESET_MODE] == "Lossnay"
    assert state.attributes[ATTR_PRESET_MODES] == ["Lossnay", "Bypass", "Auto Lossnay"]
    assert state.attributes[ATTR_PERCENTAGE] == 25
    assert state.attributes[ATTR_PERCENTAGE_STEP] == 25


async def test_unknown_preset_and_speed(
    hass: HomeAssistant, erv_api: MelViewApi, config_entry: MockConfigEntry
) -> None:
    """Values the integration does not know are shown as unknown."""
    erv_api.unit.update(power=0, setmode=5, setfan=0)
    await setup_entry(hass, config_entry)

    state = hass.states.get(FAN)
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_PRESET_MODE] is None
    assert state.attributes[ATTR_PERCENTAGE] is None


@pytest.mark.parametrize(
    ("service", "data", "commands"),
    [
        (SERVICE_TURN_ON, {}, ["PW1"]),
        (SERVICE_TURN_ON, {ATTR_PRESET_MODE: "Auto Lossnay"}, ["MD3"]),
        (SERVICE_TURN_ON, {ATTR_PERCENTAGE: 100}, ["FS6.00"]),
        (SERVICE_TURN_OFF, {}, ["PW0"]),
        (SERVICE_SET_PRESET_MODE, {ATTR_PRESET_MODE: "Bypass"}, ["MD7"]),
        (SERVICE_SET_PERCENTAGE, {ATTR_PERCENTAGE: 50}, ["FS3.00"]),
    ],
)
async def test_actions(
    hass: HomeAssistant,
    lossnay: MelViewApi,
    service: str,
    data: dict[str, Any],
    commands: list[str],
) -> None:
    """Each action sends the matching command to the unit."""
    await call(hass, service, **data)
    assert lossnay.commands == commands


async def test_preset_turns_unit_on(
    hass: HomeAssistant, erv_api: MelViewApi, config_entry: MockConfigEntry
) -> None:
    """Choosing a preset while off turns the unit on first."""
    erv_api.unit["power"] = 0
    await setup_entry(hass, config_entry)

    await call(hass, SERVICE_SET_PRESET_MODE, preset_mode="Bypass")

    assert erv_api.commands == ["PW1", "MD7"]


async def test_action_failure_raises(hass: HomeAssistant, lossnay: MelViewApi) -> None:
    """A failed fan action raises an error."""
    lossnay.status["unitcommand.aspx"] = 500

    with pytest.raises(HomeAssistantError, match="MelView command failed for Lossnay"):
        await call(hass, SERVICE_SET_PRESET_MODE, preset_mode="Bypass")
