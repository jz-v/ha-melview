"""Tests for the MelView config flow."""

from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest
from aiohttp import ClientError
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.melview.const import CONF_LOCAL, CONF_SENSOR, DOMAIN

from .conftest import EMAIL, PASSWORD, MelViewApi

USER_INPUT = {
    CONF_EMAIL: " User@Example.com ",
    CONF_PASSWORD: PASSWORD,
    CONF_LOCAL: True,
    CONF_SENSOR: False,
}

pytestmark = pytest.mark.usefixtures("mock_setup_entry")


def reject_credentials(api: MelViewApi) -> None:
    api.accept_logins = 0


def server_error(api: MelViewApi) -> None:
    api.login_status = 500


def network_error(api: MelViewApi) -> None:
    api.errors["login.aspx"] = ClientError()


def timeout(api: MelViewApi) -> None:
    api.errors["login.aspx"] = TimeoutError()


def no_units(api: MelViewApi) -> None:
    api.login_json = {"userunits": 0}


def missing_units(api: MelViewApi) -> None:
    api.login_json = {}


def unreadable_units(api: MelViewApi) -> None:
    api.login_json = {"userunits": "many"}


def unexpected_error(api: MelViewApi) -> None:
    api.errors["login.aspx"] = RuntimeError("Something unexpected")


def restore(api: MelViewApi) -> None:
    api.accept_logins = None
    api.login_status = 200
    api.login_json = {"userunits": 1}
    api.errors.clear()


async def test_user_flow(
    hass: HomeAssistant, melview_api: MelViewApi, mock_setup_entry: AsyncMock
) -> None:
    """Valid credentials create an entry with a normalised email."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == EMAIL
    assert result["data"] == {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
    assert result["options"] == {CONF_LOCAL: True, CONF_SENSOR: False}
    assert result["result"].unique_id == EMAIL
    assert len(mock_setup_entry.mock_calls) == 1


@pytest.mark.parametrize(
    ("break_api", "error"),
    [
        (reject_credentials, "invalid_auth"),
        (server_error, "cannot_connect"),
        (network_error, "cannot_connect"),
        (timeout, "cannot_connect"),
        (no_units, "no_units"),
        (missing_units, "unknown"),
        (unreadable_units, "unknown"),
        (unexpected_error, "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    break_api: Callable[[MelViewApi], None],
    error: str,
) -> None:
    """Errors are shown on the form, and the user can retry."""
    break_api(melview_api)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}
    # The form keeps what was entered, apart from the password
    assert {
        key.schema: key.description["suggested_value"]
        for key in result["data_schema"].schema
        if key.description
    } == {CONF_EMAIL: EMAIL, CONF_LOCAL: True, CONF_SENSOR: False}

    restore(melview_api)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_already_configured(
    hass: HomeAssistant, melview_api: MelViewApi, config_entry: MockConfigEntry
) -> None:
    """The same account cannot be added twice."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow(
    hass: HomeAssistant, melview_api: MelViewApi, config_entry: MockConfigEntry
) -> None:
    """Reauth asks for the new password and stores it once accepted."""
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    reject_credentials(melview_api)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "wrong"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    restore(melview_api)
    network_error(melview_api)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-password"}
    )
    assert result["errors"] == {"base": "cannot_connect"}

    restore(melview_api)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-password"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data == {CONF_EMAIL: EMAIL, CONF_PASSWORD: "new-password"}


async def test_reconfigure_flow(
    hass: HomeAssistant, melview_api: MelViewApi, config_entry: MockConfigEntry
) -> None:
    """Reconfigure changes the stored password once it is accepted."""
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    reject_credentials(melview_api)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "wrong"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    restore(melview_api)
    network_error(melview_api)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-password"}
    )
    assert result["errors"] == {"base": "cannot_connect"}

    restore(melview_api)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-password"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data == {CONF_EMAIL: EMAIL, CONF_PASSWORD: "new-password"}


async def test_options_flow(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Options default to the current values and are saved."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["data_schema"]({}) == {CONF_LOCAL: False, CONF_SENSOR: True}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_LOCAL: True, CONF_SENSOR: False}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {CONF_LOCAL: True, CONF_SENSOR: False}


async def test_options_flow_legacy_data(hass: HomeAssistant) -> None:
    """Entries from older versions kept the options in data."""
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
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["data_schema"]({}) == {CONF_LOCAL: False, CONF_SENSOR: False}
