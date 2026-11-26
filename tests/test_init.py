"""Tests for MelView setup, unload and polling."""

from collections.abc import Callable
from datetime import timedelta
import logging

from aiohttp import ClientError
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.melview import async_setup
from custom_components.melview.const import CONF_LOCAL, CONF_SENSOR, DOMAIN

from .conftest import EMAIL, PASSWORD, UNIT_ID, MelViewApi, reauth_started, setup_entry

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
    """Make login fail with a network error."""
    api.errors["login.aspx"] = ClientError()


def login_server_error(api: MelViewApi) -> None:
    """Make login fail with a server error."""
    api.login_status = 500


def unreadable_units(api: MelViewApi) -> None:
    """Report a unit count that is not a number."""
    api.login_json = {}


def rooms_server_error(api: MelViewApi) -> None:
    """Make the unit list fail with a server error."""
    api.status["rooms.aspx"] = 500


def rooms_network_error(api: MelViewApi) -> None:
    """Make the unit list fail with a network error."""
    api.errors["rooms.aspx"] = ClientError()


def no_rooms(api: MelViewApi) -> None:
    """Return an empty unit list."""
    api.rooms = []


def caps_server_error(api: MelViewApi) -> None:
    """Make unit capabilities fail with a server error."""
    api.status["unitcapabilities.aspx"] = 500


def unit_server_error(api: MelViewApi) -> None:
    """Make the unit state fail with a server error."""
    api.status["unitcommand.aspx"] = 500


def credentials_rejected(api: MelViewApi) -> None:
    """Reject the credentials at every login."""
    api.accept_logins = 0


def credentials_rejected_after_session_expires(api: MelViewApi) -> None:
    """Expire the session, then reject the credentials at the next login."""
    api.status["rooms.aspx"] = 401
    api.accept_logins = 1


def no_units(api: MelViewApi) -> None:
    """Report an account without units."""
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
    ("break_api", "reason"),
    [
        (
            rooms_server_error,
            "Unable to connect to MelView: rooms.aspx failed (status 500)",
        ),
        (no_rooms, "MelView returned an empty unit list"),
    ],
)
async def test_unit_list_failure_reason(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
    break_api: Callable[[MelViewApi], None],
    reason: str,
) -> None:
    """A failed unit list retries setup with the reason, without logging an error."""
    break_api(melview_api)
    await setup_entry(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert config_entry.reason == reason
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


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


async def test_unit_not_responding_at_setup(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A unit that is offline at setup is left out, then added when it responds."""
    melview_api.rooms[0]["units"].append({"room": "Bedroom AC", "unitid": "100002"})
    melview_api.units["100002"] = {**melview_api.unit, "fault": "COMM"}

    await setup_entry(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(CLIMATE).state != STATE_UNAVAILABLE
    assert hass.states.get("climate.bedroom_ac") is None
    assert (
        "Unit Bedroom AC is not available and will be added when it responds: "
        "Unit is not communicating with the MelView server"
    ) in caplog.text

    del melview_api.units["100002"]
    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("climate.bedroom_ac").state != STATE_UNAVAILABLE
    assert hass.states.get(CLIMATE).state != STATE_UNAVAILABLE


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


async def test_saving_options_reloads(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Changed options apply as soon as they are saved."""
    sensor = "sensor.ducted_ac_current_temperature"
    assert hass.states.get(sensor).state == "21.5"

    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_LOCAL: False, CONF_SENSOR: False}
    )
    await hass.async_block_till_done()

    # The entry reloaded without the sensor, so it is no longer provided
    assert init_integration.state is ConfigEntryState.LOADED
    assert hass.states.get(sensor).state == STATE_UNAVAILABLE


async def test_yaml_config_warns_once(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """YAML configuration is ignored with a single warning."""
    assert await async_setup(hass, {DOMAIN: {}})
    assert await async_setup(hass, {DOMAIN: {}})
    assert caplog.text.count("YAML configuration for melview") == 1


async def test_login_debug_log(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Debug logs mask the auth cookie and leave out personal details."""
    caplog.set_level(logging.DEBUG, logger="custom_components.melview")
    melview_api.login_json = {
        "id": 123456,
        "userunits": 1,
        "fullname": "Jane Citizen",
        "countryinfo": {"country": "AU"},
    }
    await setup_entry(hass, config_entry)

    assert "Auth cookie obtained: cookie-1... (29 chars)" in caplog.text
    assert melview_api.cookie not in caplog.text
    assert '"id": 123456' in caplog.text
    assert '"userunits": 1' in caplog.text
    assert "Jane Citizen" not in caplog.text
    assert "countryinfo" not in caplog.text
    assert "Login response headers" not in caplog.text


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
    coordinator = init_integration.runtime_data.coordinators[0]
    melview_api.status["unitcommand.aspx"] = 500

    for _ in range(3):
        await coordinator.async_refresh()

    assert hass.states.get(CLIMATE).state == STATE_UNAVAILABLE
    assert caplog.text.count("unitcommand.aspx failed (status 500)") == 1

    del melview_api.status["unitcommand.aspx"]
    await coordinator.async_refresh()

    assert hass.states.get(CLIMATE).state != STATE_UNAVAILABLE
    assert "Fetching MelView: Ducted AC data recovered" in caplog.text


async def test_request_that_never_answers_times_out(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    init_integration: MockConfigEntry,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A poll MelView never answers is given up on, not left hanging."""
    monkeypatch.setattr("custom_components.melview.melview.API_TIMEOUT", 0.01)
    melview_api.hang.add("unitcommand.aspx")

    await init_integration.runtime_data.coordinators[0].async_refresh()

    assert hass.states.get(CLIMATE).state == STATE_UNAVAILABLE
    assert "unitcommand.aspx timed out after 0.01 seconds" in caplog.text


async def test_login_that_never_answers_retries_setup(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    config_entry: MockConfigEntry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A login MelView never answers is given up on and setup is retried."""
    monkeypatch.setattr("custom_components.melview.melview.API_TIMEOUT", 0.01)
    melview_api.hang.add("login.aspx")

    await setup_entry(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert "Login timed out after 0.01 seconds" in config_entry.reason


async def test_comm_fault_makes_entities_unavailable(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    init_integration: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A unit that has stopped talking to MelView is unavailable."""
    melview_api.unit["fault"] = "COMM"
    await init_integration.runtime_data.coordinators[0].async_refresh()

    assert hass.states.get(CLIMATE).state == STATE_UNAVAILABLE
    assert "not communicating with the MelView server" in caplog.text


async def test_unit_faults_logged_every_poll(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    init_integration: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unit faults and errors are logged on every poll; they may be serious."""
    coordinator = init_integration.runtime_data.coordinators[0]
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


@pytest.mark.parametrize(
    ("unit_data", "message"),
    [
        (
            {"id": UNIT_ID, "error": "ok"},
            "MelView sent unit data without fault (fields received: id, error)",
        ),
        (
            {"id": UNIT_ID},
            "MelView sent unit data without fault or error (fields received: id)",
        ),
        ({}, "MelView sent unit data without fault or error (fields received: none)"),
    ],
)
async def test_unit_data_missing_fields(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    init_integration: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
    unit_data: dict,
    message: str,
) -> None:
    """Unit data without the fault and error fields says what was missing."""
    melview_api.unit = unit_data
    await init_integration.runtime_data.coordinators[0].async_refresh()

    assert hass.states.get(CLIMATE).state == STATE_UNAVAILABLE
    assert message in caplog.text


@pytest.mark.parametrize("status", [401, 503])
async def test_expired_session_logs_in_again(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    init_integration: MockConfigEntry,
    status: int,
) -> None:
    """MelView returns 401 or 503 for an expired session; log in and retry."""
    coordinator = init_integration.runtime_data.coordinators[0]
    logins = melview_api.login_count
    melview_api.status_once["unitcommand.aspx"] = [status]

    await coordinator.async_refresh()

    assert melview_api.login_count == logins + 1
    assert coordinator.last_update_success


async def test_session_still_rejected_after_login(
    hass: HomeAssistant, melview_api: MelViewApi, init_integration: MockConfigEntry
) -> None:
    """If the retry after logging in fails too, the update fails."""
    coordinator = init_integration.runtime_data.coordinators[0]
    melview_api.status["unitcommand.aspx"] = 401

    await coordinator.async_refresh()

    assert not coordinator.last_update_success
    assert not reauth_started(hass)


async def test_rejected_credentials_while_polling_start_reauth(
    hass: HomeAssistant, melview_api: MelViewApi, init_integration: MockConfigEntry
) -> None:
    """A changed password is detected while polling and starts reauth."""
    coordinator = init_integration.runtime_data.coordinators[0]
    melview_api.status["unitcommand.aspx"] = 401
    melview_api.accept_logins = melview_api.login_count

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert not coordinator.last_update_success
    assert reauth_started(hass)
