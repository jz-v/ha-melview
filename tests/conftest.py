"""Shared fixtures for MelView tests."""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from custom_components.melview.const import CONF_LOCAL, CONF_SENSOR, DOMAIN

API_URL = "https://api.melview.net/api"
EMAIL = "user@example.com"
PASSWORD = "secret"
UNIT_ID = "100001"
LOCAL_IP = "192.0.2.10"
LOCAL_URL = f"http://{LOCAL_IP}/smart"

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    """Load a JSON fixture."""
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow Home Assistant to load the integration from custom_components."""


class MelViewApi:
    """Fake MelView cloud API.

    Tests change the attributes to simulate failures. Commands sent to
    unitcommand.aspx are applied to `unit`, like a real unit would.
    """

    def __init__(self, aioclient_mock: AiohttpClientMocker) -> None:
        self._mock = aioclient_mock
        self.rooms = load_fixture("rooms.json")
        self.caps = load_fixture("unitcapabilities.json")
        self.unit = load_fixture("unitcommand.json")
        self.login_status = 200
        self.login_json: dict[str, Any] = {"userunits": 1}
        # Number of logins to accept before rejecting the credentials; None
        # accepts every login.
        self.accept_logins: int | None = None
        self.login_count = 0
        # Endpoint -> HTTP status returned on every call
        self.status: dict[str, int] = {}
        # Endpoint -> HTTP statuses returned once each, before `status` applies
        self.status_once: dict[str, list[int]] = {}
        # Endpoint -> exception raised instead of responding
        self.errors: dict[str, Exception] = {}

        aioclient_mock.post(f"{API_URL}/login.aspx", side_effect=self._login)
        for endpoint in ("rooms.aspx", "unitcapabilities.aspx", "unitcommand.aspx"):
            aioclient_mock.post(f"{API_URL}/{endpoint}", side_effect=self._api)
        aioclient_mock.post(LOCAL_URL, side_effect=self._local)

    @property
    def commands(self) -> list[str]:
        """Commands sent to the unit, in order."""
        return [
            data["commands"]
            for _, url, data, _ in self._mock.mock_calls
            if url.name == "unitcommand.aspx" and "commands" in data
        ]

    @property
    def local_commands(self) -> list[str]:
        """Payloads sent to the unit over the LAN."""
        return [data for _, url, data, _ in self._mock.mock_calls if url == LOCAL_URL]

    def _status(self, endpoint: str) -> int:
        if queued := self.status_once.get(endpoint):
            return queued.pop(0)
        return self.status.get(endpoint, 200)

    async def _login(self, method, url, data) -> AiohttpClientMockResponse:
        if exc := self.errors.get("login.aspx"):
            raise exc
        self.login_count += 1
        accepted = self.accept_logins is None or self.login_count <= self.accept_logins
        return AiohttpClientMockResponse(
            method,
            url,
            status=self.login_status,
            json=self.login_json,
            # MelView rejects credentials with a 200 and an empty auth cookie
            cookies={"auth": f"cookie-{self.login_count}" if accepted else ""},
        )

    async def _api(self, method, url, data) -> AiohttpClientMockResponse:
        endpoint = url.name
        if exc := self.errors.get(endpoint):
            raise exc
        status = self._status(endpoint)
        if endpoint == "rooms.aspx":
            body = self.rooms
        elif endpoint == "unitcapabilities.aspx":
            body = self.caps
        else:
            if status == 200 and "commands" in data:
                self._apply(data["commands"])
            body = {**self.unit, "lc": "LOCALCMD"}
        return AiohttpClientMockResponse(method, url, status=status, json=body)

    async def _local(self, method, url, data) -> AiohttpClientMockResponse:
        if exc := self.errors.get("smart"):
            raise exc
        return AiohttpClientMockResponse(method, url, status=self._status("smart"))

    def _apply(self, command: str) -> None:
        """Update the unit state the way the real unit would."""
        code, value = command[:2], command[2:]
        if code == "PW":
            self.unit["power"] = int(value)
        elif code == "MD":
            self.unit["setmode"] = int(value)
        elif code == "TS":
            self.unit["settemp"] = f"{float(value):g}"
        elif code == "FS":
            self.unit["setfan"] = int(float(value))
        elif command[0] == "Z":
            zone_id, status = int(command[1:-1]), int(command[-1])
            for zone in self.unit["zones"]:
                if zone["zoneid"] == zone_id:
                    zone["status"] = status


@pytest.fixture
def melview_api(aioclient_mock: AiohttpClientMocker) -> MelViewApi:
    """Return the fake MelView API."""
    return MelViewApi(aioclient_mock)


@pytest.fixture
def erv_api(melview_api: MelViewApi) -> MelViewApi:
    """Return the fake MelView API with a Lossnay ERV unit."""
    melview_api.caps.update(unittype="ERV", modelname="LGH-F300RVX", fanstage=4)
    melview_api.caps["hasautofan"] = 0
    melview_api.unit.update(
        setmode=1,
        setfan=2,
        roomtemp="22",
        outdoortemp="12",
        exhausttemp="15",
        coreefficiency=0.75,
    )
    return melview_api


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a MelView config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=EMAIL,
        unique_id=EMAIL,
        data={CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD},
        options={CONF_LOCAL: False, CONF_SENSOR: True},
    )


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Add the config entry to Home Assistant and set it up."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, melview_api: MelViewApi, config_entry: MockConfigEntry
) -> MockConfigEntry:
    """Set up the integration against the fake API."""
    await setup_entry(hass, config_entry)
    return config_entry


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Stop config flow tests from setting up the integration they create."""
    with patch(
        "custom_components.melview.async_setup_entry", return_value=True
    ) as mock_setup:
        yield mock_setup
