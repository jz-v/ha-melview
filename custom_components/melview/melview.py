import json
import logging
import re
import time

from aiohttp import ClientSession
from homeassistant.components.climate.const import HVACMode

from .const import APIVERSION, APPVERSION, HEADERS

_LOGGER = logging.getLogger(__name__)


LOCAL_DATA = """<?xml version="1.0" encoding="UTF-8"?>
<ESV>{}</ESV>"""

MODE = {
    HVACMode.AUTO: 8,
    HVACMode.HEAT: 1,
    HVACMode.COOL: 3,
    HVACMode.DRY: 2,
    HVACMode.FAN_ONLY: 7,
}

FANSTAGES = {
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

    def is_login(self):
        """Return login status"""
        return self._cookie is not None

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
            headers = dict(req.headers)
            auth = req.cookies.get("auth")
            if status == 200:
                self._login_json = await req.json()
        if "Set-Cookie" in headers:
            headers["Set-Cookie"] = re.sub(
                r"auth=([^;]*)",
                lambda m: f"auth={m[1][:8]}...({len(m[1])} chars)",
                headers["Set-Cookie"],
            )
        _LOGGER.debug("Login status code: %d", status)
        _LOGGER.debug("Login response headers:\n%s", json.dumps(headers, indent=2))
        _LOGGER.debug(
            "Login response json:\n%s", json.dumps(self._login_json, indent=2)
        )
        if status != 200:
            raise MelViewError(f"Login failed (status {status})")
        # Rejected credentials still return 200, but with an empty auth cookie
        if auth is None or not auth.value:
            _LOGGER.debug("Login rejected (empty auth cookie)")
            return False
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

    def __init__(
        self, deviceid, buildingid, friendlyname, authentication, localcontrol=False
    ):
        self._deviceid = deviceid
        self._buildingid = buildingid
        self._friendlyname = friendlyname
        self._authentication = authentication

        self._caps = None
        self._info_lease_seconds = 30  # Data lasts for 30s.
        self._json = None
        self._localip = localcontrol
        self._standby = 0
        self._zones = {}

        self.fan = FANSTAGES[3]
        self.halfdeg = False
        self.model = None
        self.temp_ranges = {}

    def __str__(self):
        return str(self._json)

    async def async_refresh_device_caps(self):
        self._caps = await self._authentication.async_api_post(
            "unitcapabilities.aspx", {"unitid": self._deviceid, "v": APIVERSION}
        )
        _LOGGER.debug("Unit capabilities: %s", json.dumps(self._caps, indent=2))
        if self._localip and "localip" in self._caps:
            self._localip = self._caps["localip"]
        if self._caps["fanstage"]:
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
                "Unit %s error: %s"
                "Unexpected value: please raise an Issue in the GitHub repository:"
                "https://github.com/jz-v/ha-melview/issues)",
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
        """Ensure cached unit info is fresh."""
        try:
            if self._json is None:
                return await self.async_refresh_device_info()

            if (time.time() - self._last_info_time_s) >= self._info_lease_seconds:
                _LOGGER.debug("Current settings out of date, refreshing")
                return await self.async_refresh_device_info()

        except MelViewAuthError:
            raise
        except (ConnectionError, MelViewError) as err:
            _LOGGER.debug("Info refresh failed: %s", err)
            return False

        return True

    async def async_is_caps_valid(self):
        if self._caps is None:
            return await self.async_refresh_device_caps()

        return True

    async def async_send_command(self, command):
        _LOGGER.debug("Command issued: %s", command)

        if not await self.async_is_info_valid():
            _LOGGER.error("Data outdated, command %s failed", command)
            return False

        try:
            data = await self._authentication.async_api_post(
                "unitcommand.aspx",
                {
                    "unitid": self._deviceid,
                    "v": APIVERSION,
                    "commands": command,
                    "lc": 1,
                },
            )
        except MelViewAuthError:
            raise
        except MelViewError as err:
            _LOGGER.error("Command %s failed: %s", command, err)
            return False
        _LOGGER.debug("Command sent to server")

        if self._localip:
            if "lc" in data:
                async with self._authentication.session.post(
                    f"http://{self._localip}/smart",
                    data=LOCAL_DATA.format(data["lc"]),
                ) as req:
                    if req.status == 200:
                        _LOGGER.debug("Command sent locally")
                    else:
                        _LOGGER.error("Local command failed")
            else:
                _LOGGER.error("Missing local command key")

        return True

    def get_id(self):
        """Get device ID"""
        return self._deviceid

    def get_friendly_name(self):
        """Get customised device name"""
        return self._friendlyname

    async def async_get_precision_halves(self) -> bool:
        """Get unit support for half-degree steps"""
        if not await self.async_is_caps_valid():
            return False

        return self._caps.get("halfdeg") == 1

    async def async_get_temperature(self):
        """Get set temperature"""
        if not await self.async_is_info_valid():
            return 0

        return float(self._json["settemp"])

    async def async_get_room_temperature(self):
        """Get current room temperature"""
        if not await self.async_is_info_valid():
            return 0
        return self._json.get("roomtemp", 0)

    def get_outside_temperature(self):
        """Get current outside temperature"""
        if "hasoutdoortemp" not in self._caps or self._caps["hasoutdoortemp"] == 0:
            _LOGGER.error("Outdoor temperature not supported")
            return 0
        return self._json.get("outdoortemp", 0)

    def get_unit_type(self):
        """Return the unit type from capabilities if available."""
        if self._caps is None:
            return None
        return self._caps.get("unittype")

    async def async_get_speed(self):
        """Get the set fan speed"""
        if not await self.async_is_info_valid():
            return "auto"

        for key, val in self.fan_keyed.items():
            if self._json["setfan"] == val:
                return key

        return "auto"

    async def async_get_mode(self):
        """Get the set mode (reported even when the unit is off)"""
        if not await self.async_is_info_valid():
            return HVACMode.AUTO

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
        if not await self.async_is_info_valid():
            return False

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
        if temperature < min_temp:
            _LOGGER.error(
                "Temperature %.1f lower than min %d for mode %s",
                temperature,
                min_temp,
                mode,
            )
            return False
        if temperature > max_temp:
            _LOGGER.error(
                "Temperature %.1f greater than max %d for mode %s",
                temperature,
                max_temp,
                mode,
            )
            return False
        return await self.async_send_command(f"TS{temperature:.2f}")

    async def _async_ensure_power_on(self):
        """Turn the unit on if it is off"""
        return await self.async_is_power_on() or await self.async_power_on()

    async def async_set_speed(self, speed):
        """Set the fan speed by label (fan stage name)."""
        if not await self._async_ensure_power_on():
            return False
        if speed not in self.fan_keyed:
            _LOGGER.error("Fan speed %s not supported", speed)
            return False
        return await self.async_send_command(f"FS{self.fan_keyed[speed]:.2f}")

    async def async_set_speed_code(self, speed_code):
        """Set the fan speed by code (fan stage integer)."""
        if not await self._async_ensure_power_on():
            return False
        if speed_code not in self.fan:
            _LOGGER.error("Fan speed code %d not supported", speed_code)
            return False
        return await self.async_send_command(f"FS{speed_code:.2f}")

    async def async_set_mode(self, mode):
        """Set operating mode"""
        if not await self._async_ensure_power_on():
            return False

        if mode not in MODE:
            _LOGGER.error("Mode %s not supported", mode)
            return False

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

    async def async_set_lossnay_preset(self, preset_name: str) -> bool:
        """Set Lossnay ERV preset mode."""
        code = LOSSNAY_PRESETS.get(preset_name)
        if code is None:
            _LOGGER.error("Unknown Lossnay preset: %s", preset_name)
            return False
        return await self.async_send_command(f"MD{code}")


class MelView:
    """Handler for multiple MelView devices under one user"""

    def __init__(self, authentication, localcontrol=False):
        self._authentication = authentication
        self._unitcount = 0
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
        if reply is None:
            return None

        devices = []
        for building in reply:
            for unit in building["units"]:
                device = MelViewDevice(
                    unit["unitid"],
                    building["buildingid"],
                    unit["room"],
                    self._authentication,
                    self._localcontrol,
                )
                await device.async_refresh_device_caps()
                devices.append(device)
        return devices
