"""Tests for MelView diagnostics."""

import json

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
    get_diagnostics_for_device,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.melview.const import CONF_LOCAL, CONF_SENSOR, DOMAIN

from .conftest import EMAIL, LOCAL_IP, PASSWORD, UNIT_ID, MelViewApi, setup_entry

REDACTED = "**REDACTED**"


def assert_nothing_sensitive(diagnostics: dict) -> None:
    """Check no credential, IP or ID appears anywhere in the download."""
    text = json.dumps(diagnostics)
    for secret in (EMAIL, PASSWORD, LOCAL_IP, UNIT_ID, "cookie-"):
        assert secret not in text


async def test_config_entry_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
) -> None:
    """The download covers the account and each unit, with secrets removed."""
    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, init_integration
    )

    assert_nothing_sensitive(diagnostics)
    entry = diagnostics["entry"]
    assert entry["title"] == REDACTED
    assert entry["unique_id"] == REDACTED
    assert entry["data"] == {"email": REDACTED, "password": REDACTED}
    assert entry["options"] == {CONF_LOCAL: False, CONF_SENSOR: True}
    assert diagnostics["account"] == {"units_reported": 1, "units_set_up": 1}

    [unit] = diagnostics["units"]
    assert unit["name"] == "Ducted AC"
    assert unit["capabilities"]["id"] == REDACTED
    assert unit["capabilities"]["modelname"] == "PEA-M140HAA"
    assert unit["capabilities"]["localip"] == REDACTED
    assert unit["data"]["id"] == REDACTED
    assert unit["data"]["roomtemp"] == "21.5"
    assert unit["data"]["zones"][0] == {"zoneid": 1, "name": "Lounge", "status": 1}
    assert unit["fan_speeds"] == {
        "2": "low",
        "3": "medium",
        "5": "high",
        "6": "Max",
        "0": "auto",
    }
    assert unit["temperature_ranges"]["heat"] == {"min": 17, "max": 28}
    assert unit["local_ip_found"] is False
    assert unit["last_update_success"] is True
    assert unit["last_error"] is None


async def test_diagnostics_during_outage(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    melview_api: MelViewApi,
    init_integration: MockConfigEntry,
) -> None:
    """During an outage the last error is shown, with the last good data."""
    melview_api.status["unitcommand.aspx"] = 500
    await init_integration.runtime_data[0].async_refresh()

    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, init_integration
    )

    [unit] = diagnostics["units"]
    assert unit["last_update_success"] is False
    assert unit["last_error"] == "unitcommand.aspx failed (status 500)"
    assert unit["data"]["roomtemp"] == "21.5"


async def test_diagnostics_with_local_commands(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    melview_api: MelViewApi,
    local_config_entry: MockConfigEntry,
) -> None:
    """With local commands on, diagnostics say an IP was found but not what it is."""
    await setup_entry(hass, local_config_entry)

    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, local_config_entry
    )

    assert_nothing_sensitive(diagnostics)
    assert diagnostics["units"][0]["local_ip_found"] is True


async def test_device_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
) -> None:
    """Each unit's device page has its own download."""
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, UNIT_ID), init_integration.entry_id
    )

    diagnostics = await get_diagnostics_for_device(
        hass, hass_client, init_integration, device
    )

    assert_nothing_sensitive(diagnostics)
    assert diagnostics["entry"]["data"] == {"email": REDACTED, "password": REDACTED}
    assert diagnostics["unit"]["name"] == "Ducted AC"
    assert diagnostics["unit"]["capabilities"]["modelname"] == "PEA-M140HAA"
