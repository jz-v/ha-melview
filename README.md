# Home Assistant - Mitsubishi Electric Wi-Fi Control

<p align="left">
  <img src="https://github.com/jz-v/ha-melview/blob/master/logo.png" alt="Mitsubishi Electric Logo" height="75" align="middle" />
  <img src="https://github.com/jz-v/ha-melview/blob/master/adapter.png" alt="Adapter" height="192" align="middle" />
</p>

## General
This is a Home Assistant integration for [AU/NZ Mitsubishi Electric Air Conditioners with a Wi-Fi adapter](https://www.mitsubishielectric.com.au/product/wi-fi-controller/).

Benefits of this integration compared with others:
 - faster (local) commands
 - group entities into HA devices (useful for ducted systems with zone switches)
 - optional 'current temperature' sensor entity
 - per device/mode min-max temperature ranges
 - detect and show standy/preheating operation
 - options UI to toggle 0.5 deg temp step, local commands, and sensor entity
 - far fewer API calls, particularly with multiple zones or devices.
 - Lossnay ERV units exposed as fan entities with additional sensors

## Installation
Note: please completely remove any existing custom components for melview prior to installing this.

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
Mitsubishi Wi-Fi adaptors in this region require an internet connection at all times to function.

However, it is possible for commands to be sent locally (i.e. from Home Assistant to the Wi-Fi adaptor over LAN):
 - First, the command must be sent to the melview server, requesting a local command key
 - Response received with local command key
 - Local command key is sent to the adapter via LAN.

In practice, this is still much quicker than waiting up to 30 seconds for the adapter to check in with the melview server to receive commands.

For truly local control, these adapters are also compatible with the ECHONETLite protocol, which has a [very well maintained HACS integration](https://github.com/scottyphillips/echonetlite_homeassistant). However, be aware that the ECHONETLite protocol does not support ZONES in any way, nor 0.5 deg temperature steps.

## Attributions
 - Forked from https://github.com/haggis663/ha-melview (WTFPL licensed)
 - Original repository https://github.com/zacharyrs/ha-melview (WTFPL licensed)
 - Original reverse-engineering of melview API via https://github.com/NovaGL/diy-melview

## License
This project is licensed under the MIT License.

