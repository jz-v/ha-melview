"""Sleep timer support for MelView devices.

The Wi-Fi Control app offers a "Sleep timer" that powers a unit down after a
chosen number of minutes. The command behind it is undocumented, but the app is
a Cordova wrapper around the web client at app.melview.net, whose JavaScript is
served unminified. From js/ex.js:

    if (self.powerOffIn() >= 0) postcommand += ',PT' + self.powerOffIn();   # :7582
    ...
    if (typeof data.sleeptimer !== 'undefined') {                           # :7794
        self.powerOffAt(new Date(data.sleeptimer));

So the timer is a ``PT<minutes>`` command in the same comma-separated command
string already used for PW/MD/TS/FS, and the resulting power-off time comes back
as a ``sleeptimer`` field on the unitcommand.aspx reply. ``PT0`` cancels.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import SLEEP_TIMER_MAX_MINUTES, SLEEP_TIMER_STEP_MINUTES
from .entity import MelViewBaseEntity

_LOGGER = logging.getLogger(__name__)

# Some responses use the ASP.NET "/Date(1756100000000)/" form rather than ISO.
_MS_DATE = re.compile(r"^/Date\((-?\d+)([+-]\d{4})?\)/$")


def parse_sleep_timer(raw) -> datetime | None:
    """Parse a ``sleeptimer`` value into an aware UTC datetime.

    Returns None when no timer is set or the value cannot be parsed; callers
    must not read that as "the timer has finished".
    """
    if raw in (None, "", 0, "0"):
        return None

    if isinstance(raw, (int, float)):
        return dt_util.utc_from_timestamp(raw / 1000 if raw > 1e11 else raw)

    text = str(raw).strip()

    ms_date = _MS_DATE.match(text)
    if ms_date:
        return dt_util.utc_from_timestamp(int(ms_date.group(1)) / 1000)

    parsed = dt_util.parse_datetime(text)
    if parsed is None:
        _LOGGER.warning("Unrecognised sleeptimer value: %r", raw)
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)

    return dt_util.as_utc(parsed)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a sleep timer control per MelView device."""
    coordinators = entry.runtime_data

    async_add_entities(
        [MelViewSleepTimerNumber(coordinator) for coordinator in coordinators],
        update_before_add=True,
    )


class MelViewSleepTimerNumber(MelViewBaseEntity, NumberEntity):
    """Minutes until the unit powers itself off. 0 means no timer."""

    _attr_has_entity_name = True
    _attr_name = "Sleep Timer"
    _attr_icon = "mdi:timer-outline"
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 0
    _attr_native_step = SLEEP_TIMER_STEP_MINUTES
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, coordinator) -> None:
        """Initialize the control, tied to a DataUpdateCoordinator."""
        super().__init__(coordinator, coordinator.device)
        self._attr_unique_id = f"{coordinator.device.get_id()}_sleep_timer"
        self._attr_native_max_value = SLEEP_TIMER_MAX_MINUTES
        # Retained only until the unit reports a sleeptimer back.
        self._requested: int | None = None

    @property
    def available(self) -> bool:
        """Only expose the timer while the unit is on.

        MelView discards a sleep timer whenever a unit reports power off, and
        the app disables its own timer button in that state (ex.js:8092).
        """
        if not super().available:
            return False
        return bool((self.coordinator.data or {}).get("power", 0))

    @property
    def native_value(self) -> float | None:
        """Return the minutes remaining before the unit powers off."""
        raw = self._device.get_sleep_timer_end()
        if not raw:
            self._requested = None
            return 0

        end = parse_sleep_timer(raw)
        if end is None:
            # A timer exists but the value was not understood.
            return self._requested

        remaining = (end - dt_util.utcnow()).total_seconds() / 60
        return max(0, round(remaining))

    @property
    def extra_state_attributes(self) -> dict:
        """Expose the absolute power-off time."""
        end = parse_sleep_timer(self._device.get_sleep_timer_end())
        return {"powers_off_at": end.isoformat() if end else None}

    async def async_set_native_value(self, value: float) -> None:
        """Start, change or (with 0) cancel the sleep timer."""
        minutes = int(round(value))
        if await self._device.async_set_sleep_timer(minutes):
            self._requested = minutes or None
            await self.coordinator.async_request_refresh()
