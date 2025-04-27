# Home Assistant - Mitsubishi Electric Wi-Fi Control
## General
This is a custom integration for Home Assistant for AU/NZ Mitsubishi Electric Air Conditioners with an app.melview.net Wi-Fi adapter.
Supports climate entity and zone control via switch entities.

https://www.mitsubishielectric.com.au/product/wi-fi-controller/

Main benefits of this integration compared with others:
 - local commands
 - group entities into device(s)
 - additional options UI (i.e. to toggle 0.5 deg temp step, local commands)

## About 'Local commands'
Mitsubishi Wi-Fi adaptors in this region require an internet connection at all times to function.

However, it is possible for commands to be sent locally (i.e. from Home Assistant to the Wi-Fi adaptor over LAN):
 - First, the command must be sent to the melview server, requesting a local command key
 - Response received with local command key
 - Local command key is sent to the adapter.

In practice, this is still much quicker than having commands sent to adapter from the melview cloud server.

## Tested Devices
I have personally tested on the following combination:
 - PEA-M140HAA ducted air conditioning unit
 - MAC-568IF-E wi-fi adapter

However, the compatibility is likely much greater than this.

## Attributions
 - Forked from https://github.com/haggis663/ha-melview (WTFPL licensed)
 - Original repository https://github.com/zacharyrs/ha-melview (WTFPL licensed)
 - Original reverse-engineering of melview API via https://github.com/NovaGL/diy-melview licensed under the WTFPL

## Installation
Install via HACS, remember to restart Home Assistant after HACS install to allow this integration to be added from Settings/Integrations. 

## License
This project is licensed under the MIT License.