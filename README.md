# Home Assistant - Mitsubishi Electric Wi-Fi Control

<p align="left">
  <img src="https://github.com/jz-v/ha-melview/blob/master/logo.png" alt="Mitsubishi Electric Logo" height="75" align="middle" />
  <img src="https://github.com/jz-v/ha-melview/blob/master/adapter.png" alt="Adapter" height="192" align="middle" />
</p>

## General
Home Assistant integration for [AU/NZ Mitsubishi Electric Air Conditioners with a Wi-Fi adapter](https://www.mitsubishielectric.com.au/product/wi-fi-controller/).

Features:
 - fast (local) commands
 - zone control support (for ducted systems)
 - standby/preheating detection
 - optional 'current temperature' sensor entity
 - Lossnay ERV support (experimental, see below)

Note: this integration will only work for units in Australia and New Zealand.

## Installation
Please completely remove any existing custom components for melview prior to installing this one.

1. Install and set up HACS (hacs.xyz)
2. Click this button to open in HACS:

   [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?repository=ha-melview&owner=jz-v)

3. Click the 'Download' button in the lower right corner, then 'Download' button at the prompt.
4. Restart Home Assistant
5. Click this button to add the Integration:

   [![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=melview)


## Compatible devices
This integration is intended to work with any AU/NZ region Wi-Fi adapter connecting to the melview API:
 - MAC-568IF-E
 - MAC-578IF-E
 - MAC-588IF-E.

Personally tested on the following combination:
 - PEA-M140HAA ducted air conditioning unit
 - MAC-568IF-E Wi-Fi adapter.


## About 'local commands'
These Wi-Fi adapters require an internet connection, however, it is possible for commands to be 'pushed' locally over LAN:
 - First, command is sent to the melview server, requesting a local command key
 - Response received with local command key
 - Local command key is sent to the adapter via LAN.

In practice, this is still much quicker than waiting up to 30 seconds for the adapter to check in with the melview server to receive commands.

For truly local control, these adapters are also compatible with the ECHONETLite protocol, which has a [very well maintained HACS integration](https://github.com/scottyphillips/echonetlite_homeassistant). However, the ECHONETLite protocol does not support zones, nor 0.5 deg temperature steps.

## Lossnay support
Lossnay ERV units with Wi-Fi Control can now be added as a unique device.
Devices include a **fan entity** with adjustable speed and presets, as well as additional sensors for:  
- Outdoor temperature  
- Supply temperature  
- Exhaust temperature  
- Core efficiency.

Support is experimental due to limited testing. If you encounter a problem please open an Issue and include debug logs.

## Attributions
 - Forked from https://github.com/haggis663/ha-melview (WTFPL licensed)
 - Original repository https://github.com/zacharyrs/ha-melview (WTFPL licensed)
 - Original reverse-engineering of melview API via https://github.com/NovaGL/diy-melview

## License
This project is licensed under the MIT License.

