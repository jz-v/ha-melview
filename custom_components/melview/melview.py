import json
import logging
import time
from aiohttp import ClientSession
from .const import APPVERSION, HEADERS, APIVERSION

from homeassistant.components.climate.const import (
    HVACMode
)

_LOGGER = logging.getLogger(__name__)

LOCAL_DATA = """<?xml version="1.0" encoding="UTF-8"?>
<ESV>{}</ESV>"""

MODE = {
    HVACMode.AUTO: 8,
    HVACMode.HEAT: 1,
    HVACMode.COOL: 3,
    HVACMode.DRY: 2,
    HVACMode.FAN_ONLY: 7
}

FANSTAGES = {
    1: {5: "on"},
    2: {2: "low", 5: "high"},
    3: {2: "low", 3: "medium", 5: "high"},
    4: {2: "low", 3: "medium", 5: "high", 6: "Max"},
    5: {1: "low", 2: "medium", 3: "Medium High", 5: "high", 6: "Max"},
}

class MelViewAuthentication:
    """Implementation to remember and refresh MelView cookies."""
    def __init__(self, email, password):
        self._email = email
        self._password = password
        self._cookie = None

    def is_login(self):
        """Return login status"""
        return self._cookie is not None

    async def  asynclogin(self):
        """Generate a new login cookie"""
        _LOGGER.debug("Trying to login")
        self._cookie = None
        async with ClientSession() as session:
            req = await session.post('https://api.melview.net/api/login.aspx',
                    json={'user': self._email, 'pass': self._password,
                          'appversion': APPVERSION},
                    headers=HEADERS) 
        _LOGGER.debug("Login status code: %d", req.status)
        _LOGGER.debug("Login response headers:\n%s", json.dumps(dict(req.headers), indent=2))
        _LOGGER.debug("Login response json:\n%s", json.dumps(await req.json(), indent=2))
        if req.status == 200:
            cks = req.cookies
            if 'auth' in cks:
                auth_value = cks['auth'].value
                if auth_value:
                    self._cookie = auth_value
                    return True
                else:
                    _LOGGER.error("Invalid auth cookie")
                    _LOGGER.error("Login status code: %d", req.status)
                    _LOGGER.error("Login response headers:\n%s", json.dumps(dict(req.headers), indent=2))
                    _LOGGER.error("Login response json:\n%s", json.dumps(await req.json(), indent=2))                    
                    return False
            _LOGGER.error("Missing auth cookie")
            _LOGGER.error("Login status code: %d", req.status)
            _LOGGER.error("Login response headers:\n%s", json.dumps(dict(req.headers), indent=2))
            _LOGGER.error("Login response json:\n%s", json.dumps(await req.json(), indent=2))
        else:
            _LOGGER.error("Invalid response status")            
            _LOGGER.error("Login status code: %d", req.status)
            _LOGGER.error("Login response headers:\n%s", json.dumps(dict(req.headers), indent=2))
            _LOGGER.error("Login response json:\n%s", json.dumps(await req.json(), indent=2))
        return False

    def get_cookie(self):
        """Return authentication cookie"""
        return {'auth': self._cookie}


class MelViewZone:
    def __init__(self, id, name, status):
        self.id = id
        self.name = name
        self.status = status


class MelViewDevice:
    """Handler class for a MelView unit"""
    def __init__(self, deviceid, buildingid, friendlyname,
                 authentication, localcontrol=False):
        self._deviceid = deviceid
        self._buildingid = buildingid
        self._friendlyname = friendlyname
        self._authentication = authentication

        self._caps = None
        self._localip = localcontrol

        self._info_lease_seconds = 30  # Data lasts for 30s.
        self._json = None
        self._zones = {}
        self._standby = 0

        self.fan = FANSTAGES[3]
        self.temp_ranges = {}
        self.model = None
    
    async def async_refresh(self):
        await self.async_refresh_device_caps()
        await self.async_refresh_device_info()    

    def __str__(self):
        return str(self._json)

    async def async_refresh_device_caps(self, retry=True):
        self._json = None
        self._last_info_time_s = time.time()

        async with ClientSession() as session:
            req = await session.post('https://api.melview.net/api/unitcapabilities.aspx',
                            cookies=self._authentication.get_cookie(),
                            json={'unitid': self._deviceid, 'v': APIVERSION})
        if req.status == 200:
            self._caps = await req.json()
            if self._localip and 'localip' in self._caps:
                self._localip = self._caps['localip']
            if self._caps['fanstage']:
                self.fan = FANSTAGES[self._caps['fanstage']]
            if 'hasautofan' in self._caps and self._caps['hasautofan'] == 1:
                self.fan[0] = 'auto'
            self.fan_keyed = {value: key for key, value in self.fan.items()}
            if "max" in self._caps:
                for hvac_mode, mode_id in MODE.items():
                    caps_range = self._caps["max"].get(str(mode_id))
                    if caps_range and "min" in caps_range and "max" in caps_range:
                        self.temp_ranges[hvac_mode] = {
                            "min": caps_range["min"],
                            "max": caps_range["max"],
                        }
            if 'modelname' in self._caps:
                self.model = self._caps['modelname']
            return True
        if req.status == 401 and retry:
            _LOGGER.error("Unit capabilities error 401 (trying to re-login)")
            if await self._authentication.asynclogin():
                return await self.async_refresh_device_caps(retry=False)
        else:
            _LOGGER.error("Unable to retrieve unit capabilities"
                          "(Invalid status code: %d)", req.status)
        return False
   
    async def async_refresh_device_info(self, retry=True):
        self._json = None
        self._last_info_time_s = time.time()

        async with ClientSession() as session:
            req = await session.post('https://api.melview.net/api/unitcommand.aspx',
                            cookies=self._authentication.get_cookie(),
                            json={'unitid': self._deviceid, 'v': APIVERSION})
        if req.status == 200:
            self._json = await req.json()
            if 'zones' in self._json:
                self._zones = {z['zoneid'] : MelViewZone(z['zoneid'], z['name'], z['status']) for z in self._json['zones']}
            if 'standby' in self._json:
                self._standby = self._json['standby']
            if 'error' in self._json:
                if self._json['error'] != 'ok':
                    _LOGGER.error("Unit error: %s", self._json['error'])
            if 'fault' in self._json:
                if self._json['fault'] != '':
                    _LOGGER.error("Unit fault: %s", self._json['fault'])
            return True
        if req.status == 401 and retry:
            _LOGGER.error("Info error 401 (trying to re-login)")
            if await self._authentication.asynclogin():
                return await self.async_refresh_device_info(retry=False)
        else:
            _LOGGER.error("Unable to retrieve info (invalid status code: %d)",
                          req.status)
        return False

    async def async_is_info_valid(self):
        if self._json is None:
            return await self.async_refresh_device_info()

        if (time.time() - self._last_info_time_s) >= self._info_lease_seconds:
            _LOGGER.debug("Current settings out of date, refreshing")
            return await self.async_refresh_device_info()

        return True
        
    async def async_is_caps_valid(self):
        if self._caps is None:
            return await self.async_refresh_device_caps()

        return True
        
    async def async_send_command(self, command, retry=True):
        _LOGGER.debug("Command issued: %s", command)

        if not await self.async_is_info_valid():
            _LOGGER.error("Data outdated, command %s failed", command)
            return False

        async with ClientSession() as session:
            req = await session.post('https://api.melview.net/api/unitcommand.aspx',
                            cookies=self._authentication.get_cookie(),
                            json={'unitid': self._deviceid, 'v': APIVERSION,
                                  'commands': command, 'lc': 1})
        if req.status == 200:
            _LOGGER.debug("Command sent to server")

            resp = await req.json()
            if self._localip:
                if 'lc' in resp:
                    local_command = resp['lc']
                    async with ClientSession() as session:
                        req = await session.post('http://{}/smart'.format(self._localip),
                                        data=LOCAL_DATA.format(local_command))
                    if req.status == 200:
                        _LOGGER.debug("Command sent locally")
                    else:
                        _LOGGER.error("Local command failed")
                else:
                    _LOGGER.error("Missing local command key")

            return True
        if req.status == 401 and retry:
            _LOGGER.error("Command send error 401 (trying to relogin)")
            if await self._authentication.asynclogin():
                return await self.async_send_command(command, retry=False)
        else:
            _LOGGER.error("Unable to send command (invalid status code: %d",
                          req.status)

        return False

    async def async_force_update(self):
        """Force info refresh"""
        return await self.async_refresh_device_info()

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

        return float(self._json['settemp'])

    async def async_get_room_temperature(self):
        """Get current room temperature"""
        if not await self.async_is_info_valid():
            return 0
        return self._json.get('roomtemp', 0)

    def get_outside_temperature(self):
        """Get current outside temperature"""
        if not 'hasoutdoortemp' in self._caps or self._caps['hasoutdoortemp'] == 0:
            _LOGGER.error("Outdoor temperature not supported")
            return 0
        return self._json.get('outdoortemp', 0)

    async def async_get_speed(self):
        """Get the set fan speed"""
        if not await self.async_is_info_valid():
            return "auto"

        for key, val in self.fan_keyed.items():
            if self._json['setfan'] == val:
                return key

        return "auto"

    async def async_get_mode(self):
        """Get the set mode"""
        if not await self.async_is_info_valid():
            return HVACMode.AUTO

        if await self.async_is_power_on():
            for key, val in MODE.items():
                if self._json['setmode'] == val:
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

        return self._json['power']

    async def async_set_temperature(self, temperature):
        """Set the target temperature"""
        mode = await self.async_get_mode()
        temp_range = self.temp_ranges.get(mode)
        if not temp_range:
            _LOGGER.warning("No temperature range available for mode %s", mode.value)
            return await self.async_send_command('TS{:.2f}'.format(temperature))
        min_temp = temp_range["min"]
        max_temp = temp_range["max"]
        if temperature < min_temp:
            _LOGGER.error("Temperature %.1f lower than min %d for mode %s",
                          temperature, min_temp, mode)
            return False
        if temperature > max_temp:
            _LOGGER.error("Temperature %.1f greater than max %d for mode %s",
                          temperature, max_temp, mode)
            return False
        return await self.async_send_command('TS{:.2f}'.format(temperature))

    async def async_set_speed(self, speed):
        """Set the fan speed"""
        if not await self.async_is_power_on():
            # Try turn on the unit if off.
            if not await self.async_power_on():
                return False

        if speed not in self.fan_keyed.keys():
            _LOGGER.error("Fan speed %d not supported", speed)
            return False
        return await self.async_send_command('FS{:.2f}'.format(self.fan_keyed[speed]))

    async def async_set_mode(self, mode):
        """Set operating mode"""
        if not await self.async_is_power_on():
            # Try turn on the unit if off.
            if not await self.async_power_on():
                return False

        if mode == "Auto" and (not 'hasautomode' in self._caps or self._caps['hasautomode'] == 0):
            _LOGGER.error("Auto mode not supported")
            return False
        if mode == "Dry" and (not 'hasdrymode' in self._caps or self._caps['hasdrymode'] == 0):
            _LOGGER.error("Dry mode not supported")
            return False
        if mode != "Cool" and ('hascoolonly' in self._caps and self._caps['hascoolonly'] == 1):
            _LOGGER.error("Only cool mode supported")
            return False
        if mode not in MODE.keys():
            _LOGGER.error("Mode %d not supported", mode)
            return False
        return await self.async_send_command('MD{}'.format(MODE[mode]))

    async def async_enable_zone(self, zoneid):
        """Turn on a zone"""
        return await self.async_send_command(f"Z{zoneid}1")

    async def async_disable_zone(self, zoneid):
        """Turn off a zone"""
        return await self.async_send_command(f"Z{zoneid}0")

    async def async_power_on(self):
        """Turn on the unit"""
        return await self.async_send_command('PW1')
        
    async def async_power_off(self):
        """Turn off the unit"""
        return await self.async_send_command('PW0')


class MelView:
    """Handler for multiple MelView devices under one user"""
    def __init__(self, authentication, localcontrol=False):
        self._authentication = authentication
        self._unitcount = 0
        self._localcontrol = localcontrol

    async def async_get_devices_list(self, retry=True):
        """Return all the devices found, as handlers"""
        devices = []

        async with ClientSession() as session:
            req = await session.post('https://api.melview.net/api/rooms.aspx',
                            json={'unitid': 0},
                            headers=HEADERS,
                            cookies=self._authentication.get_cookie())
        if req.status == 200:
            reply = await req.json()
            for building in reply:
                for unit in building['units']:
                    melViewDevice= MelViewDevice(unit['unitid'],
                                                 building['buildingid'],
                                                 unit['room'],
                                                 self._authentication,
                                                 self._localcontrol)
                    await melViewDevice.async_refresh()
                    devices.append(melViewDevice)

        elif req.status == 401 and retry:
            _LOGGER.error("Device list error 401 (trying to re-login)")
            if await self._authentication.asynclogin():
                return await self.async_get_devices_list(retry=False)
        else:
            _LOGGER.error("Failed to get device list (status code invalid: %d)",
                          req.status)

        return devices
