import json
import logging
import time
from asyncio import timeout

from aiohttp import ClientError, ClientSession
from homeassistant.components.climate.const import HVACMode

from .const import APIVERSION, APPVERSION, HEADERS

_LOGGER = logging.getLogger(__name__)


LOCAL_DATA = """<?xml version="1.0" encoding="UTF-8"?>
<ESV>{}</ESV>"""

# Seconds to wait for the adapter to accept a command over the LAN
LOCAL_TIMEOUT = 5

# Personal details in the login response, left out of debug logs
LOGIN_PERSONAL_FIELDS = ("fullname", "countryinfo")

MODE = {
    HVACMode.AUTO: 8,
    HVACMode.HEAT: 1,
    HVACMode.COOL: 3,
    HVACMode.DRY: 2,
    HVACMode.FAN_ONLY: 7,
}

FANSTAGES = {
    0: {},
    1: {5: "on"},
    2: {2: "low", 5: "high"},
    3: {2: "low", 3: "medium", 5: "high"},
    4: {2: "low", 3: "medium", 5: "high", 6: "Max"},
    5: {1: "low", 2: "medium", 3: "Medium High", 5: "high", 6: "Max"},
}

LOSSNAY_PRESETS = {
    "Lossnay": 1,
    "Bypass": 7,
    "Auto Lossnay": 3,
}


class MelViewError(Exception):
    """Error communicating with the MelView API."""


class MelViewAuthError(MelViewError):
    """MelView rejected the account credentials."""


class MelViewValidationError(MelViewError):
    """A command was rejected because its input is not valid for the unit."""


class MelViewAuthentication:
    """Implementation to remember and refresh MelView cookies."""

    def __init__(self, email, password, session: ClientSession):
        self._email = email
        self._password = password
        self._session = session
        self._cookie = None
        self._login_json = None

    @property
    def session(self) -> ClientSession:
        """Return the shared HTTP session"""
        return self._session

    async def async_login(self):
        """Generate a new login cookie.

        Return False if the credentials are rejected; raise MelViewError if
        the server returns an error status.
        """
        _LOGGER.debug("Trying to login")
        self._cookie = None
        self._login_json = None
        async with self._session.post(
            "https://api.melview.net/api/login.aspx",
            json={
                "user": self._email,
                "pass": self._password,
                "appversion": APPVERSION,
            },
            headers=HEADERS,
        ) as req:
            status = req.status
            auth = req.cookies.get("auth")
            if status == 200:
                self._login_json = await req.json()
        _LOGGER.debug("Login status code: %d", status)
        if status != 200:
            raise MelViewError(f"Login failed (status {status})")
        _LOGGER.debug(
            "Login response json:\n%s",
            json.dumps(
                {
                    key: value
                    for key, value in self._login_json.items()
                    if key not in LOGIN_PERSONAL_FIELDS
                },
                indent=2,
            ),
        )
        # Rejected credentials still return 200, but with an empty auth cookie
        if auth is None or not auth.value:
            _LOGGER.debug("Login rejected (empty auth cookie)")
            return False
        _LOGGER.debug(
            "Auth cookie obtained: %s... (%d chars)", auth.value[:8], len(auth.value)
        )
        self._cookie = auth.value
        return True

    def get_cookie(self):
        """Return authentication cookie"""
        return {"auth": self._cookie}

    async def async_api_post(self, endpoint, payload, *, headers=None, retry=True):
        """POST to the MelView API and return the JSON response.

        On 401 or 503 (MelView returns 503 for an invalidated session), log in
        again once; raise MelViewAuthError if the credentials are rejected.
        Raise MelViewError for any other failure status; callers polling via
        the coordinator rely on it to log the failure once, not every update.
        """
        async with self._session.post(
            f"https://api.melview.net/api/{endpoint}",
            json=payload,
            headers=headers,
            cookies=self.get_cookie(),
        ) as resp:
            if resp.status == 200:
                return await resp.json()
            status = resp.status
        if status in (401, 503) and retry:
            _LOGGER.debug("%s returned %d, logging in again", endpoint, status)
            if not await self.async_login():
                raise MelViewAuthError("MelView rejected the stored credentials")
            return await self.async_api_post(
                endpoint, payload, headers=headers, retry=False
            )
        raise MelViewError(f"{endpoint} failed (status {status})")

    def number_units(self):
        """Return the number of units in login response."""
        if not self._login_json:
            return False
        try:
            return int(self._login_json.get("userunits", 0))
        except (AttributeError, TypeError, ValueError):
            return False


class MelViewZone:
    def __init__(self, id, name, status):
        self.id = id
        self.name = name
        self.status = status


class MelViewDevice:
    """Handler class for a MelView unit"""

    def __init__(self, deviceid, friendlyname, authentication, localcontrol=False):
        self._deviceid = deviceid
        self._friendlyname = friendlyname
        self._authentication = authentication

        self._caps = None
        self._info_lease_seconds = 30  # Data lasts for 30s.
        self._json = None
        self._localcontrol = localcontrol
        self._localip = None
        self._standby = 0
        self._zones = {}

        self.fan = dict(FANSTAGES[3])
        self.halfdeg = False
        self.model = None
        self.temp_ranges = {}

    async def async_refresh_device_caps(self):
        self._caps = await self._authentication.async_api_post(
            "unitcapabilities.aspx", {"unitid": self._deviceid, "v": APIVERSION}
        )
        _LOGGER.debug("Unit capabilities: %s", json.dumps(self._caps, indent=2))
        if self._localcontrol:
            self._localip = self._caps.get("localip")
            if not self._localip:
                _LOGGER.warning(
                    "%s did not report a local IP address, so commands will "
                    "only be sent through MelView",
                    self.get_friendly_name(),
                )
        # Fanstage 0 means the unit has no fan control, e.g. air-to-water units
        if self._caps.get("fanstage") in FANSTAGES:
            self.fan = dict(FANSTAGES[self._caps["fanstage"]])
        if "hasautofan" in self._caps and self._caps["hasautofan"] == 1:
            self.fan[0] = "auto"
        self.fan_keyed = {value: key for key, value in self.fan.items()}
        if "max" in self._caps:
            for hvac_mode, mode_id in MODE.items():
                caps_range = self._caps["max"].get(str(mode_id))
                if caps_range and "min" in caps_range and "max" in caps_range:
                    self.temp_ranges[hvac_mode] = {
                        "min": caps_range["min"],
                        "max": caps_range["max"],
                    }
                    if hvac_mode == HVACMode.COOL:
                        self.temp_ranges[HVACMode.DRY] = dict(
                            self.temp_ranges[HVACMode.COOL]
                        )
        if "modelname" in self._caps:
            self.model = self._caps["modelname"]
        if "halfdeg" in self._caps and self._caps["halfdeg"] == 1:
            self.halfdeg = True
        if "error" in self._caps and self._caps["error"] != "ok":
            _LOGGER.warning(
                "%s unit capabilities error: %s, attempting to continue",
                self.get_friendly_name(),
                self._caps["error"],
            )
        if "fault" in self._caps and self._caps["fault"] != "":
            _LOGGER.warning(
                "%s unit capabilities fault: %s, attempting to continue",
                self.get_friendly_name(),
                self._caps["fault"],
            )
        return True

    async def async_refresh_device_info(self):
        self._json = None
        self._last_info_time_s = time.time()

        self._json = await self._authentication.async_api_post(
            "unitcommand.aspx", {"unitid": self._deviceid, "v": APIVERSION}
        )

        fault = self._json["fault"]
        error = self._json["error"]
        if fault == "COMM":
            raise ConnectionError(
                "Unit is not communicating with the MelView server (COMM fault). "
                "Check the adapter is connected to Wi-Fi with an internet connection. "
                "For further troubleshooting, refer to the Mitsubishi Electric "
                "Wi-Fi Control adapter User Manual."
            )
        if fault != "":
            _LOGGER.warning(
                "Unit %s fault: %s",
                self.get_friendly_name(),
                fault,
            )
        if error != "ok":
            _LOGGER.warning(
                "Unit %s error: %s. Unexpected value, please raise an issue at "
                "https://github.com/jz-v/ha-melview/issues",
                self.get_friendly_name(),
                error,
            )

        if "zones" in self._json:
            self._zones = {
                z["zoneid"]: MelViewZone(z["zoneid"], z["name"], z["status"])
                for z in self._json["zones"]
            }
        if "standby" in self._json:
            self._standby = self._json["standby"]
        return True

    async def async_is_info_valid(self):
        """Ensure cached unit info is fresh; raise if it cannot be refreshed."""
        if self._json is None:
            return await self.async_refresh_device_info()

        if (time.time() - self._last_info_time_s) >= self._info_lease_seconds:
            _LOGGER.debug("Current settings out of date, refreshing")
            return await self.async_refresh_device_info()

        return True

    async def async_send_command(self, command):
        """Send a command to the unit; raise if it cannot be sent."""
        _LOGGER.debug("Command issued: %s", command)

        await self.async_is_info_valid()

        data = await self._authentication.async_api_post(
            "unitcommand.aspx",
            {
                "unitid": self._deviceid,
                "v": APIVERSION,
                "commands": command,
                "lc": 1,
            },
        )
        _LOGGER.debug("Command sent to server")

        if self._localip:
            await self._async_send_local_command(data.get("lc"))

    async def _async_send_local_command(self, key):
        """Push a command MelView has accepted straight to the adapter.

        Problems are only logged: the adapter still collects the command from
        MelView at its next check-in.
        """
        if key is None:
            _LOGGER.error("Missing local command key")
            return
        try:
            async with (
                timeout(LOCAL_TIMEOUT),
                self._authentication.session.post(
                    f"http://{self._localip}/smart", data=LOCAL_DATA.format(key)
                ) as req,
            ):
                status = req.status
        except (ClientError, TimeoutError) as err:
            _LOGGER.warning(
                "Local command to %s at %s not delivered (%s); the unit will "
                "get it from MelView instead",
                self.get_friendly_name(),
                self._localip,
                str(err) or "timed out",
            )
            return
        if status == 200:
            _LOGGER.debug("Command sent locally")
        else:
            _LOGGER.error("Local command failed")

    def get_id(self):
        """Get device ID"""
        return self._deviceid

    def get_friendly_name(self):
        """Get customised device name"""
        return self._friendlyname

    def get_unit_type(self):
        """Return the unit type from capabilities."""
        return self._caps.get("unittype")

    async def async_get_mode(self):
        """Get the set mode (reported even when the unit is off)"""
        await self.async_is_info_valid()

        for key, val in MODE.items():
            if self._json["setmode"] == val:
                return key

        return HVACMode.AUTO

    def get_zone(self, zoneid):
        return self._zones.get(zoneid)

    def get_zones(self):
        return self._zones.values()

    async def async_is_power_on(self):
        """Check unit is on"""
        await self.async_is_info_valid()

        return self._json["power"]

    async def async_set_temperature(self, temperature):
        """Set the target temperature"""
        mode = await self.async_get_mode()
        temp_range = self.temp_ranges.get(mode)
        if not temp_range:
            _LOGGER.warning("No temperature range available for mode %s", mode.value)
            return await self.async_send_command(f"TS{temperature:.2f}")
        min_temp = temp_range["min"]
        max_temp = temp_range["max"]
        if not min_temp <= temperature <= max_temp:
            raise MelViewValidationError(
                f"Temperature {temperature:.1f} is outside the range "
                f"{min_temp} to {max_temp} for {mode.value} mode"
            )
        return await self.async_send_command(f"TS{temperature:.2f}")

    async def _async_ensure_power_on(self):
        """Turn the unit on if it is off"""
        if not await self.async_is_power_on():
            await self.async_power_on()

    async def async_set_speed(self, speed):
        """Set the fan speed by label (fan stage name)."""
        if speed not in self.fan_keyed:
            raise MelViewValidationError(f"Fan speed {speed} not supported")
        await self._async_ensure_power_on()
        return await self.async_send_command(f"FS{self.fan_keyed[speed]:.2f}")

    async def async_set_speed_code(self, speed_code):
        """Set the fan speed by code (fan stage integer)."""
        if speed_code not in self.fan:
            raise MelViewValidationError(f"Fan speed code {speed_code} not supported")
        await self._async_ensure_power_on()
        return await self.async_send_command(f"FS{speed_code:.2f}")

    async def async_set_mode(self, mode):
        """Set operating mode"""
        if mode not in MODE:
            raise MelViewValidationError(f"Mode {mode} not supported")
        await self._async_ensure_power_on()
        return await self.async_send_command(f"MD{MODE[mode]}")

    async def async_enable_zone(self, zoneid):
        """Turn on a zone"""
        return await self.async_send_command(f"Z{zoneid}1")

    async def async_disable_zone(self, zoneid):
        """Turn off a zone"""
        return await self.async_send_command(f"Z{zoneid}0")

    async def async_power_on(self):
        """Turn on the unit"""
        return await self.async_send_command("PW1")

    async def async_power_off(self):
        """Turn off the unit"""
        return await self.async_send_command("PW0")

    async def async_set_lossnay_preset(self, preset_name: str) -> None:
        """Set Lossnay ERV preset mode."""
        code = LOSSNAY_PRESETS.get(preset_name)
        if code is None:
            raise MelViewValidationError(f"Unknown Lossnay preset {preset_name}")
        return await self.async_send_command(f"MD{code}")


class MelView:
    """Handler for multiple MelView devices under one user"""

    def __init__(self, authentication, localcontrol=False):
        self._authentication = authentication
        self._localcontrol = localcontrol

    async def async_get_devices_list(self):
        """Return all the devices found, as handlers"""
        try:
            reply = await self._authentication.async_api_post(
                "rooms.aspx", {"unitid": 0}, headers=HEADERS
            )
        except MelViewAuthError:
            raise
        except Exception as err:  # noqa: BLE001 - any failure means "not ready, retry"
            _LOGGER.error("Device list request failed: %s", err)
            return None

        devices = []
        for building in reply:
            for unit in building["units"]:
                device = MelViewDevice(
                    unit["unitid"],
                    unit["room"],
                    self._authentication,
                    self._localcontrol,
                )
                await device.async_refresh_device_caps()
                devices.append(device)
        return devices
