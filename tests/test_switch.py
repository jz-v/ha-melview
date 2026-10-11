"""Tests for the MelView zone switches."""

import pytest
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import MelViewApi, setup_entry

LOUNGE = "switch.ducted_ac_zone_lounge"
BEDROOM = "switch.ducted_ac_zone_bedroom"
STUDY = "switch.ducted_ac_zone_study"


async def test_zone_states(
    hass: HomeAssistant, melview_api: MelViewApi, config_entry: MockConfigEntry
) -> None:
    """Each zone is a switch; a spilling zone is on with spill active."""
    melview_api.unit["zones"].append({"zoneid": 3, "name": "Study", "status": 2})
    await setup_entry(hass, config_entry)

    assert hass.states.get(LOUNGE).state == STATE_ON
    assert hass.states.get(LOUNGE).attributes["Spill active"] is False
    assert hass.states.get(BEDROOM).state == STATE_OFF
    assert hass.states.get(STUDY).state == STATE_ON
    assert hass.states.get(STUDY).attributes["Spill active"] is True


async def test_turn_zones_on_and_off(
    hass: HomeAssistant, melview_api: MelViewApi, init_integration: MockConfigEntry
) -> None:
    """Switching a zone sends its command and updates the state."""
    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: BEDROOM}, blocking=True
    )
    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: LOUNGE}, blocking=True
    )

    assert melview_api.commands == ["Z21", "Z10"]
    assert hass.states.get(BEDROOM).state == STATE_ON
    assert hass.states.get(LOUNGE).state == STATE_OFF


async def test_zone_no_longer_reported(
    hass: HomeAssistant, melview_api: MelViewApi, init_integration: MockConfigEntry
) -> None:
    """A zone the unit stops reporting is unavailable until it comes back."""
    coordinator = init_integration.runtime_data[0]
    bedroom = melview_api.unit["zones"].pop()

    await coordinator.async_refresh()
    assert hass.states.get(BEDROOM).state == STATE_UNAVAILABLE
    assert hass.states.get(LOUNGE).state == STATE_ON

    melview_api.unit["zones"].append(bedroom)
    await coordinator.async_refresh()
    assert hass.states.get(BEDROOM).state == STATE_OFF


async def test_zone_action_failure_raises(
    hass: HomeAssistant, melview_api: MelViewApi, init_integration: MockConfigEntry
) -> None:
    """A failed zone change raises an error."""
    melview_api.status["unitcommand.aspx"] = 500

    with pytest.raises(HomeAssistantError, match="unitcommand.aspx failed"):
        await hass.services.async_call(
            SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: BEDROOM}, blocking=True
        )
