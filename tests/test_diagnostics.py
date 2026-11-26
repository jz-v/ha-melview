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

from custom_components.melview.const import CONF_LOCAL, DOMAIN

from .conftest import EMAIL, LOCAL_IP, PASSWORD, UNIT_ID, MelViewApi, setup_entry


def assert_no_credentials(diagnostics: dict) -> None:
    """Check the email, password and auth cookie appear nowhere in the download."""
    text = json.dumps(diagnostics)
    for secret in (EMAIL, PASSWORD, "cookie-"):
        assert secret not in text


async def test_config_entry_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
) -> None:
    """The download covers the account and each unit, without credentials."""
    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, init_integration
    )

    assert_no_credentials(diagnostics)
    entry = diagnostics["entry"]
    assert "title" not in entry
    assert "unique_id" not in entry
    assert entry["data"] == {}
    assert entry["options"] == {CONF_LOCAL: False}
    assert diagnostics["account"] == {"units_reported": 1, "units_set_up": 1}
    assert diagnostics["units_not_responding"] == []

    [unit] = diagnostics["units"]
    assert unit["name"] == "Ducted AC"
    assert unit["capabilities"]["id"] == UNIT_ID
    assert unit["capabilities"]["modelname"] == "PEA-M140HAA"
    assert unit["capabilities"]["localip"] == LOCAL_IP
    assert unit["data"]["id"] == UNIT_ID
    assert unit["data"]["roomtemp"] == "21.5"
    assert unit["fan_speeds"] == {
        "2": "low",
        "3": "medium",
        "5": "high",
        "6": "Max",
        "0": "auto",
    }
    assert unit["temperature_ranges"]["heat"] == {"min": 17, "max": 28}
    assert unit["last_update_success"] is True
    assert unit["last_error"] is None


async def test_zone_names_left_out(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
) -> None:
    """Zones show number and status only; names can be people's names."""
    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, init_integration
    )

    [unit] = diagnostics["units"]
    assert unit["capabilities"]["zones"][0] == {
        "zoneid": 1,
        "status": 1,
        "display": 1,
    }
    assert unit["data"]["zones"] == [
        {"zoneid": 1, "status": 1},
        {"zoneid": 2, "status": 0},
    ]
    assert "Lounge" not in json.dumps(diagnostics)
    # The live data the zone switches use still has the names
    assert (
        init_integration.runtime_data.coordinators[0].data["zones"][0]["name"]
        == "Lounge"
    )
    assert hass.states.get("switch.ducted_ac_zone_lounge")


async def test_unit_without_zones(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    melview_api: MelViewApi,
    config_entry: MockConfigEntry,
) -> None:
    """Units without zones are included as reported."""
    del melview_api.caps["zones"], melview_api.unit["zones"]
    await setup_entry(hass, config_entry)

    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, config_entry
    )

    [unit] = diagnostics["units"]
    assert "zones" not in unit["capabilities"]
    assert "zones" not in unit["data"]


async def test_diagnostics_during_outage(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    melview_api: MelViewApi,
    init_integration: MockConfigEntry,
) -> None:
    """During an outage the last error is shown, with the last good data."""
    melview_api.status["unitcommand.aspx"] = 500
    await init_integration.runtime_data.coordinators[0].async_refresh()

    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, init_integration
    )

    [unit] = diagnostics["units"]
    assert unit["last_update_success"] is False
    assert unit["last_error"] == "unitcommand.aspx failed (status 500)"
    assert unit["data"]["roomtemp"] == "21.5"


async def test_device_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
) -> None:
    """Each unit's device page has its own download."""
    # Looked up this way so the test runs on every supported Home Assistant version
    device = next(
        device
        for device in dr.async_entries_for_config_entry(
            dr.async_get(hass), init_integration.entry_id
        )
        if (DOMAIN, UNIT_ID) in device.identifiers
    )

    diagnostics = await get_diagnostics_for_device(
        hass, hass_client, init_integration, device
    )

    assert_no_credentials(diagnostics)
    assert diagnostics["entry"]["data"] == {}
    assert diagnostics["unit"]["name"] == "Ducted AC"
    assert diagnostics["unit"]["capabilities"]["modelname"] == "PEA-M140HAA"
    assert diagnostics["set_up"] is True


async def test_unit_not_responding_at_setup(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    melview_api: MelViewApi,
    config_entry: MockConfigEntry,
) -> None:
    """A unit left out at setup is in both downloads, with the reason."""
    melview_api.login_json = {"userunits": 2}
    melview_api.rooms[0]["units"].append({"room": "Bedroom AC", "unitid": "100002"})
    melview_api.units["100002"] = {**melview_api.unit, "fault": "COMM"}
    # The unit's device is left from when it last loaded
    config_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id, identifiers={(DOMAIN, "100002")}
    )
    await setup_entry(hass, config_entry)

    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, config_entry
    )

    assert diagnostics["account"] == {"units_reported": 2, "units_set_up": 1}
    [unit] = diagnostics["units"]
    assert unit["name"] == "Ducted AC"
    [unit] = diagnostics["units_not_responding"]
    assert unit["name"] == "Bedroom AC"
    assert unit["capabilities"]["modelname"] == "PEA-M140HAA"
    assert unit["data"] is None
    assert unit["last_update_success"] is False
    assert unit["last_error"].startswith(
        "Unit is not communicating with the MelView server (COMM fault)"
    )

    diagnostics = await get_diagnostics_for_device(
        hass, hass_client, config_entry, device
    )

    assert diagnostics["unit"]["name"] == "Bedroom AC"
    assert diagnostics["set_up"] is False


async def test_device_diagnostics_for_removed_unit(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
) -> None:
    """A device for a unit no longer in the account still has a download."""
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=init_integration.entry_id, identifiers={(DOMAIN, "999999")}
    )

    diagnostics = await get_diagnostics_for_device(
        hass, hass_client, init_integration, device
    )

    assert diagnostics["entry"]["data"] == {}
    assert diagnostics["unit"] is None
    assert diagnostics["set_up"] is False
