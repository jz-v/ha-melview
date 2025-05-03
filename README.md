# Home Assistant - Mitsubishi Electric Wi-Fi Control
## General
This is a custom integration for Home Assistant for AU/NZ Mitsubishi Electric Air Conditioners with an app.melview.net Wi-Fi adapter.
Supports climate entity and zone control via switch entities.

https://www.mitsubishielectric.com.au/product/wi-fi-controller/

Main benefits of this integration compared with others:
 - local commands
 - group entities into device(s)
 - create 'current temperature' sensor entity
 - read min/max temp ranges from device
 - configure options UI, e.g. to toggle 0.5 deg temp step, local commands, and sensor entity

## About 'Local commands'
Mitsubishi Wi-Fi adaptors in this region require an internet connection at all times to function.

However, it is possible for commands to be sent locally (i.e. from Home Assistant to the Wi-Fi adaptor over LAN):
 - First, the command must be sent to the melview server, requesting a local command key
 - Response received with local command key
 - Local command key is sent to the adapter via LAN.

In practice, this is still much quicker than having commands sent to adapter from the melview cloud server.

## Tested Devices
I have personally tested on the following combination:
 - PEA-M140HAA ducted air conditioning unit
 - MAC-568IF-E wi-fi adapter

However, the compatibility is likely much greater than this.

## Installation
1. Set up HACS (hacs.xyz)
2. Add this as a custom repository in HACS
3. Install via HACS interface
4. Restart Home Assistant after HACS install
5. Add this integration from Settings > Devices & services > Add integrations.

Currently working towards inclusion in HACS default repositories to make this easier.

## Future improvements
I would like to add the following features/ functionality in future:
- Choice of entity for Zone control (i.e. choose between switch or fan entity)
- Support for HVAC action, e.g. report when unit is in defrosting, etc.

## Attributions
 - Forked from https://github.com/haggis663/ha-melview (WTFPL licensed)
 - Original repository https://github.com/zacharyrs/ha-melview (WTFPL licensed)
 - Original reverse-engineering of melview API via https://github.com/NovaGL/diy-melview licensed under the WTFPL

## License
This project is licensed under the MIT License.

