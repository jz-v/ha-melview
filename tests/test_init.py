"""Tests for MelView setup, unload and polling."""

import logging
from collections.abc import Callable

import pytest
from aiohttp import ClientError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.melview import async_setup
from custom_components.melview.const import CONF_LOCAL, CONF_SENSOR, DOMAIN

from .conftest import (
    EMAIL,
    PASSWORD,
    UNIT_ID,
    MelViewApi,
    reauth_started,
    setup_entry,
)

CLIMATE = "climate.ducted_ac"


async def test_setup_and_unload(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The entry loads, creates entities and unloads."""
    assert init_integration.state is ConfigEntryState.LOADED
    assert hass.states.get(CLIMATE)

    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.NOT_LOADED


def login_network_error(api: MelViewApi) -> None:
    api.errors["login.aspx"] = ClientError()


def login_server_error(api: MelViewApi) -> None:
    api.login_status = 500


def unreadable_units(api: MelViewApi) -> None:
    api.login_json = {}


def rooms_server_error(api: MelViewApi) -> None:
    api.status["rooms.aspx"] = 500


def rooms_network_error(api: MelViewApi) -> None:
    api.errors["rooms.aspx"] = ClientError()


def no_rooms(api: MelViewApi) -> None:
    api.rooms = []


def caps_server_error(api: MelViewApi) -> None:
    api.status["unitcapabilities.aspx"] = 500


def unit_server_error(api: MelViewApi) -> None:
    api.status["unitcommand.aspx"] = 500


def credentials_rejected(api: MelViewApi) -> None:
    api.accept_logins = 0


def credentials_rejected_after_session_expires(api: MelViewApi) -> None:
    api.status["rooms.aspx"] = 401
    api.accept_logins = 1


def no_units(api: MelViewApi) -> None:
    api.login_json = {"userunits": 0}


@pytest.mark.parametrize(
    ("break_api", "state"),
    [
        (login_network_error, ConfigEntryState.SETUP_RETRY),
        (login_server_error, ConfigEntryState.SETUP_RETRY),
        (unreadable_units, ConfigEntryState.SETUP_RETRY),
        (rooms_server_error, ConfigEntryState.SETUP_RETRY),
        (rooms_network_error, ConfigEntryState.SETUP_RETRY),
        (no_rooms, ConfigEntryState.SETUP_RETRY),
        (caps_server_error, ConfigEntryState.SETUP_RETRY),
        (unit_server_error, ConfigEntryState.SETUP_RETRY),
        (credentials_rejected, ConfigEntryState.SETUP_ERROR),
        (credentials_rejected_after_session_expires, ConfigEntryState.SETUP_ERROR),
        (no_units, ConfigEntryState.SETUP_ERROR),
    ],
)
async def test_setup_failures(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    config_entry: MockConfigEntry,
    break_api: Callable[[MelViewApi], None],
    state: ConfigEntryState,
) -> None:
    """Connection problems retry setup; account problems stop it."""
    break_api(melview_api)
    await setup_entry(hass, config_entry)
    assert config_entry.state is state


@pytest.mark.parametrize(
    "break_api", [credentials_rejected, credentials_rejected_after_session_expires]
)
async def test_setup_rejected_credentials_start_reauth(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    config_entry: MockConfigEntry,
    break_api: Callable[[MelViewApi], None],
) -> None:
    """Rejected credentials during setup ask the user to log in again."""
    break_api(melview_api)
    await setup_entry(hass, config_entry)
    assert reauth_started(hass)


async def test_removed_units_are_cleaned_up(
    hass: HomeAssistant, melview_api: MelViewApi, config_entry: MockConfigEntry
) -> None:
    """Devices for units no longer in the account are removed at setup."""
    device_registry = dr.async_get(hass)
    config_entry.add_to_hass(hass)
    current = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id, identifiers={(DOMAIN, UNIT_ID)}
    )
    stale = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id, identifiers={(DOMAIN, "999999")}
    )
    other = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id, identifiers={("other", "abc")}
    )

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert device_registry.async_get(current.id) is not None
    assert device_registry.async_get(stale.id) is None
    assert device_registry.async_get(other.id) is not None


async def test_account_without_units_removes_devices(
    hass: HomeAssistant, melview_api: MelViewApi, config_entry: MockConfigEntry
) -> None:
    """An account with no units removes all its devices."""
    device_registry = dr.async_get(hass)
    config_entry.add_to_hass(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id, identifiers={(DOMAIN, UNIT_ID)}
    )
    no_units(melview_api)

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert device_registry.async_get(device.id) is None


async def test_options_moved_out_of_data(
    hass: HomeAssistant, melview_api: MelViewApi
) -> None:
    """Older entries stored the options in data; setup moves them."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=EMAIL,
        data={
            CONF_EMAIL: EMAIL,
            CONF_PASSWORD: PASSWORD,
            CONF_LOCAL: False,
            CONF_SENSOR: False,
        },
    )
    await setup_entry(hass, entry)

    assert entry.data == {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
    assert entry.options == {CONF_LOCAL: False, CONF_SENSOR: False}


async def test_yaml_config_warns_once(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """YAML configuration is ignored with a single warning."""
    assert await async_setup(hass, {DOMAIN: {}})
    assert await async_setup(hass, {DOMAIN: {}})
    assert caplog.text.count("YAML configuration for melview") == 1


async def test_auth_cookie_masked_in_debug_log(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Debug logs show only the start of the auth cookie."""
    caplog.set_level(logging.DEBUG, logger="custom_components.melview")
    melview_api.login_headers = {"Set-Cookie": "auth=0123456789abcdef; path=/"}
    await setup_entry(hass, config_entry)

    assert "auth=01234567...(16 chars); path=/" in caplog.text
    assert "0123456789abcdef" not in caplog.text


async def test_unit_capability_warnings(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Capability errors and faults are logged but setup continues."""
    melview_api.caps.update(error="E1", fault="F2")
    await setup_entry(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert "Ducted AC unit capabilities error: E1" in caplog.text
    assert "Ducted AC unit capabilities fault: F2" in caplog.text


async def test_outage_logged_once_then_recovery(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    init_integration: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An outage makes entities unavailable and is logged once (log-when-unavailable)."""
    caplog.set_level(logging.INFO)
    coordinator = init_integration.runtime_data[0]
    melview_api.status["unitcommand.aspx"] = 500

    for _ in range(3):
        await coordinator.async_refresh()

    assert hass.states.get(CLIMATE).state == STATE_UNAVAILABLE
    assert caplog.text.count("unitcommand.aspx failed (status 500)") == 1

    del melview_api.status["unitcommand.aspx"]
    await coordinator.async_refresh()

    assert hass.states.get(CLIMATE).state != STATE_UNAVAILABLE
    assert "Fetching MelView: Ducted AC data recovered" in caplog.text


async def test_comm_fault_makes_entities_unavailable(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    init_integration: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A unit that has stopped talking to MelView is unavailable."""
    melview_api.unit["fault"] = "COMM"
    await init_integration.runtime_data[0].async_refresh()

    assert hass.states.get(CLIMATE).state == STATE_UNAVAILABLE
    assert "not communicating with the MelView server" in caplog.text


async def test_unit_faults_logged_every_poll(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    init_integration: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unit faults and errors are logged on every poll; they may be serious."""
    coordinator = init_integration.runtime_data[0]
    melview_api.unit.update(fault="E6", error="E7")

    await coordinator.async_refresh()
    await coordinator.async_refresh()

    assert hass.states.get(CLIMATE).state != STATE_UNAVAILABLE
    assert caplog.text.count("Unit Ducted AC fault: E6") == 2
    assert (
        caplog.text.count(
            "Unit Ducted AC error: E7. Unexpected value, please raise an issue at "
            "https://github.com/jz-v/ha-melview/issues\n"
        )
        == 2
    )


@pytest.mark.parametrize("status", [401, 503])
async def test_expired_session_logs_in_again(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    init_integration: MockConfigEntry,
    status: int,
) -> None:
    """MelView returns 401 or 503 for an expired session; log in and retry."""
    coordinator = init_integration.runtime_data[0]
    logins = melview_api.login_count
    melview_api.status_once["unitcommand.aspx"] = [status]

    await coordinator.async_refresh()

    assert melview_api.login_count == logins + 1
    assert coordinator.last_update_success


async def test_session_still_rejected_after_login(
    hass: HomeAssistant, melview_api: MelViewApi, init_integration: MockConfigEntry
) -> None:
    """If the retry after logging in fails too, the update fails."""
    coordinator = init_integration.runtime_data[0]
    melview_api.status["unitcommand.aspx"] = 401

    await coordinator.async_refresh()

    assert not coordinator.last_update_success
    assert not reauth_started(hass)


async def test_rejected_credentials_while_polling_start_reauth(
    hass: HomeAssistant, melview_api: MelViewApi, init_integration: MockConfigEntry
) -> None:
    """A changed password is detected while polling and starts reauth."""
    coordinator = init_integration.runtime_data[0]
    melview_api.status["unitcommand.aspx"] = 401
    melview_api.accept_logins = melview_api.login_count

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert not coordinator.last_update_success
    assert reauth_started(hass)
