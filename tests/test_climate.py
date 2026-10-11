"""Tests for the MelView climate entity."""

from collections.abc import Callable
from typing import Any

import pytest
from aiohttp import ClientError
from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_HVAC_MODES,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_TARGET_TEMP_STEP,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    ATTR_TEMPERATURE,
    STATE_OFF,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import MelViewApi, reauth_started, setup_entry

CLIMATE = "climate.ducted_ac"


async def call(hass: HomeAssistant, service: str, **data: Any) -> None:
    """Call a climate action on the test entity."""
    await hass.services.async_call(
        CLIMATE_DOMAIN, service, {ATTR_ENTITY_ID: CLIMATE, **data}, blocking=True
    )


async def test_state(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """The unit's settings are shown on the entity."""
    state = hass.states.get(CLIMATE)

    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_CURRENT_TEMPERATURE] == 21.5
    assert state.attributes[ATTR_TEMPERATURE] == 20
    assert state.attributes[ATTR_FAN_MODE] == "medium"
    assert state.attributes[ATTR_FAN_MODES] == ["low", "medium", "high", "Max", "auto"]
    assert state.attributes[ATTR_HVAC_MODES] == [
        HVACMode.AUTO,
        HVACMode.HEAT,
        HVACMode.COOL,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
        HVACMode.OFF,
    ]
    assert state.attributes[ATTR_MIN_TEMP] == 17
    assert state.attributes[ATTR_MAX_TEMP] == 28
    assert state.attributes[ATTR_TARGET_TEMP_STEP] == 0.5
    assert state.attributes.get(ATTR_HVAC_ACTION) is None
    assert (
        state.attributes[ATTR_SUPPORTED_FEATURES]
        & ClimateEntityFeature.TARGET_TEMPERATURE
    )


async def test_state_off(
    hass: HomeAssistant, melview_api: MelViewApi, config_entry: MockConfigEntry
) -> None:
    """A unit that is off shows as off."""
    melview_api.unit["power"] = 0
    await setup_entry(hass, config_entry)

    state = hass.states.get(CLIMATE)
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.OFF


@pytest.mark.parametrize(
    ("unit", "action"),
    [
        ({"setmode": 1, "standby": 1}, HVACAction.PREHEATING),
        ({"setmode": 7}, HVACAction.FAN),
        ({"setmode": 3}, None),
    ],
)
async def test_hvac_action(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    config_entry: MockConfigEntry,
    unit: dict[str, int],
    action: HVACAction | None,
) -> None:
    """Pre-heating and fan-only are reported; other actions are not known."""
    melview_api.unit.update(unit)
    await setup_entry(hass, config_entry)

    assert hass.states.get(CLIMATE).attributes.get(ATTR_HVAC_ACTION) == action


async def test_fan_only_mode(
    hass: HomeAssistant, melview_api: MelViewApi, config_entry: MockConfigEntry
) -> None:
    """Fan-only mode has no target temperature or temperature range."""
    melview_api.unit["setmode"] = 7
    await setup_entry(hass, config_entry)

    state = hass.states.get(CLIMATE)
    assert state.state == HVACMode.FAN_ONLY
    assert not (
        state.attributes[ATTR_SUPPORTED_FEATURES]
        & ClimateEntityFeature.TARGET_TEMPERATURE
    )
    assert state.attributes[ATTR_MIN_TEMP] == 7
    assert state.attributes[ATTR_MAX_TEMP] == 35


async def test_unknown_fan_code(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A fan code the unit does not support has no fan mode."""
    melview_api.unit["setfan"] = 4
    await setup_entry(hass, config_entry)

    assert hass.states.get(CLIMATE).attributes[ATTR_FAN_MODE] is None
    assert "Fan code 4 not present in available modes" in caplog.text


@pytest.mark.parametrize(
    ("service", "data", "commands"),
    [
        (SERVICE_TURN_ON, {}, ["PW1"]),
        (SERVICE_TURN_OFF, {}, ["PW0"]),
        (SERVICE_SET_HVAC_MODE, {ATTR_HVAC_MODE: HVACMode.COOL}, ["MD3"]),
        (SERVICE_SET_HVAC_MODE, {ATTR_HVAC_MODE: HVACMode.OFF}, ["PW0"]),
        (SERVICE_SET_TEMPERATURE, {ATTR_TEMPERATURE: 22.5}, ["TS22.50"]),
        (
            SERVICE_SET_TEMPERATURE,
            {ATTR_TEMPERATURE: 25, ATTR_HVAC_MODE: HVACMode.COOL},
            ["MD3", "TS25.00"],
        ),
        (SERVICE_SET_FAN_MODE, {ATTR_FAN_MODE: "high"}, ["FS5.00"]),
    ],
)
async def test_actions(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    init_integration: MockConfigEntry,
    service: str,
    data: dict[str, Any],
    commands: list[str],
) -> None:
    """Each action sends the matching command to the unit."""
    await call(hass, service, **data)
    assert melview_api.commands == commands


async def test_actions_update_state(
    hass: HomeAssistant, melview_api: MelViewApi, init_integration: MockConfigEntry
) -> None:
    """The entity shows the new settings straight after an action."""
    await call(hass, SERVICE_SET_TEMPERATURE, temperature=24, hvac_mode=HVACMode.COOL)
    await call(hass, SERVICE_SET_FAN_MODE, fan_mode="high")

    state = hass.states.get(CLIMATE)
    assert state.state == HVACMode.COOL
    assert state.attributes[ATTR_TEMPERATURE] == 24
    assert state.attributes[ATTR_FAN_MODE] == "high"


@pytest.mark.parametrize(
    ("service", "data", "commands"),
    [
        (SERVICE_SET_HVAC_MODE, {ATTR_HVAC_MODE: HVACMode.COOL}, ["PW1", "MD3"]),
        (SERVICE_SET_FAN_MODE, {ATTR_FAN_MODE: "high"}, ["PW1", "FS5.00"]),
    ],
)
async def test_mode_and_fan_turn_unit_on(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    config_entry: MockConfigEntry,
    service: str,
    data: dict[str, Any],
    commands: list[str],
) -> None:
    """Changing mode or fan speed turns the unit on first."""
    melview_api.unit["power"] = 0
    await setup_entry(hass, config_entry)

    await call(hass, service, **data)
    assert melview_api.commands == commands


async def test_temperature_checked_against_new_mode(
    hass: HomeAssistant, melview_api: MelViewApi, init_integration: MockConfigEntry
) -> None:
    """A temperature valid for heat but not cool is rejected after the mode change."""
    with pytest.raises(ServiceValidationError, match="outside the range 19 to 30"):
        await call(hass, SERVICE_SET_TEMPERATURE, temperature=18, hvac_mode="cool")
    assert melview_api.commands == ["MD3"]


async def test_temperature_without_range_for_mode(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A temperature is still sent if the unit reports no range for the mode."""
    del melview_api.caps["max"]["8"]
    melview_api.unit["setmode"] = 8
    await setup_entry(hass, config_entry)

    await call(hass, SERVICE_SET_TEMPERATURE, temperature=22)

    assert melview_api.commands == ["TS22.00"]
    assert "No temperature range available for mode auto" in caplog.text


def expire_cached_data(entry: MockConfigEntry) -> None:
    """Age the cached unit data past its 30 second lease."""
    entry.runtime_data[0].device._last_info_time_s -= 60


async def test_command_refreshes_expired_data_first(
    hass: HomeAssistant, melview_api: MelViewApi, init_integration: MockConfigEntry
) -> None:
    """Stale unit data is refreshed before a command is sent."""
    melview_api.unit["power"] = 0  # changed since the last poll
    expire_cached_data(init_integration)

    await call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.COOL)

    assert melview_api.commands == ["PW1", "MD3"]


async def test_comm_fault_blocks_commands(
    hass: HomeAssistant, melview_api: MelViewApi, init_integration: MockConfigEntry
) -> None:
    """A unit that has stopped talking to MelView explains why commands fail."""
    melview_api.unit["fault"] = "COMM"
    expire_cached_data(init_integration)

    with pytest.raises(HomeAssistantError, match="Check the adapter is connected"):
        await call(hass, SERVICE_TURN_ON)
    assert melview_api.commands == []


def server_error(api: MelViewApi) -> None:
    api.status["unitcommand.aspx"] = 500


def network_error(api: MelViewApi) -> None:
    api.errors["unitcommand.aspx"] = ClientError("Connection reset")


def timeout(api: MelViewApi) -> None:
    api.errors["unitcommand.aspx"] = TimeoutError()


@pytest.mark.parametrize("break_api", [server_error, network_error, timeout])
async def test_action_failure_raises(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    init_integration: MockConfigEntry,
    break_api: Callable[[MelViewApi], None],
) -> None:
    """A failed action raises an error instead of failing silently."""
    break_api(melview_api)
    with pytest.raises(
        HomeAssistantError, match="MelView command failed for Ducted AC"
    ):
        await call(hass, SERVICE_TURN_ON)


async def test_action_rejected_credentials_start_reauth(
    hass: HomeAssistant, melview_api: MelViewApi, init_integration: MockConfigEntry
) -> None:
    """Rejected credentials during an action raise and start reauth."""
    melview_api.status["unitcommand.aspx"] = 401
    melview_api.accept_logins = melview_api.login_count

    with pytest.raises(HomeAssistantError, match="rejected the stored credentials"):
        await call(hass, SERVICE_TURN_ON)
    await hass.async_block_till_done()

    assert reauth_started(hass)


async def test_local_commands(
    hass: HomeAssistant, melview_api: MelViewApi, local_config_entry: MockConfigEntry
) -> None:
    """With local commands on, each command is also sent to the unit over the LAN."""
    await setup_entry(hass, local_config_entry)

    await call(hass, SERVICE_TURN_ON)

    assert melview_api.local_commands == [
        '<?xml version="1.0" encoding="UTF-8"?>\n<ESV>LOCALCMD</ESV>'
    ]


@pytest.mark.parametrize(
    ("break_local", "message"),
    [
        (lambda api: api.status.update(smart=500), "Local command failed"),
        (lambda api: setattr(api, "local_command", None), "Missing local command key"),
    ],
)
async def test_local_command_problems_are_logged(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    local_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
    break_local: Callable[[MelViewApi], None],
    message: str,
) -> None:
    """The cloud command already went through, so local problems only log."""
    await setup_entry(hass, local_config_entry)
    break_local(melview_api)

    await call(hass, SERVICE_TURN_ON)

    assert melview_api.commands == ["PW1"]
    assert message in caplog.text
