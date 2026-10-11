"""Tests for the MelView sensors."""

import pytest
from homeassistant.components.climate import ATTR_CURRENT_TEMPERATURE
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.melview.const import CONF_SENSOR, DOMAIN

from .conftest import EMAIL, MelViewApi, setup_entry

CLIMATE = "climate.ducted_ac"
ROOM_TEMP = "sensor.ducted_ac_current_temperature"


async def test_current_temperature(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The room temperature has its own sensor."""
    state = hass.states.get(ROOM_TEMP)
    assert state.state == "21.5"
    assert state.attributes["unit_of_measurement"] == "°C"
    assert state.attributes["device_class"] == "temperature"
    assert "source" not in state.attributes


async def test_sensor_option_off(
    hass: HomeAssistant, melview_api: MelViewApi, config_entry: MockConfigEntry
) -> None:
    """No sensors are created when the option is off."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=EMAIL,
        data=config_entry.data,
        options={**config_entry.options, CONF_SENSOR: False},
    )
    await setup_entry(hass, entry)

    assert hass.states.get(CLIMATE)
    assert hass.states.get(ROOM_TEMP) is None


async def test_missing_temperature_is_unknown(
    hass: HomeAssistant, melview_api: MelViewApi, config_entry: MockConfigEntry
) -> None:
    """A missing reading is unknown, not 0 °C."""
    del melview_api.unit["roomtemp"]
    await setup_entry(hass, config_entry)

    assert hass.states.get(ROOM_TEMP).state == STATE_UNKNOWN
    assert hass.states.get(CLIMATE).attributes[ATTR_CURRENT_TEMPERATURE] is None


async def test_invalid_temperature_is_unknown(
    hass: HomeAssistant,
    melview_api: MelViewApi,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A reading that is not a number is unknown and logged."""
    melview_api.unit["roomtemp"] = "--"
    await setup_entry(hass, config_entry)

    assert hass.states.get(ROOM_TEMP).state == STATE_UNKNOWN
    assert "Invalid roomtemp value: --" in caplog.text


async def test_lossnay_sensors(
    hass: HomeAssistant, erv_api: MelViewApi, config_entry: MockConfigEntry
) -> None:
    """Lossnay units get air temperature and core efficiency sensors."""
    await setup_entry(hass, config_entry)

    assert hass.states.get("sensor.lossnay_current_temperature").state == "22.0"
    assert hass.states.get("sensor.lossnay_fresh_air").state == "12.0"
    assert hass.states.get("sensor.lossnay_stale_air").state == "15.0"
    # Fresh air warmed by the core: 12 + 0.75 * (22 - 12)
    assert hass.states.get("sensor.lossnay_pre_warmed").state == "19.5"
    assert hass.states.get("sensor.lossnay_core_efficiency").state == "75.0"
    assert hass.states.get("climate.lossnay") is None


@pytest.mark.parametrize(
    ("missing", "unknown"),
    [
        ("outdoortemp", ["sensor.lossnay_fresh_air", "sensor.lossnay_pre_warmed"]),
        (
            "coreefficiency",
            ["sensor.lossnay_core_efficiency", "sensor.lossnay_pre_warmed"],
        ),
    ],
)
async def test_lossnay_missing_readings(
    hass: HomeAssistant,
    erv_api: MelViewApi,
    config_entry: MockConfigEntry,
    missing: str,
    unknown: list[str],
) -> None:
    """Sensors that depend on a missing reading are unknown."""
    del erv_api.unit[missing]
    await setup_entry(hass, config_entry)

    for entity_id in unknown:
        assert hass.states.get(entity_id).state == STATE_UNKNOWN
    assert hass.states.get("sensor.lossnay_stale_air").state == "15.0"
