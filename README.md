# Home Assistant - Mitsubishi Electric Wi-Fi Control

This is a custom integration for Home Assistant for AU/NZ Mitsubishi Electric Air Conditioners with an app.melview.net Wi-Fi adapter.
Supports climate entity and zone control via switch entities.

https://www.mitsubishielectric.com.au/product/wi-fi-controller/

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
 - Forked from https://github.com/haggis663/ha-melview
 - Original repository https://github.com/zacharyrs/ha-melview
 - Original reverse-engineering of API via https://github.com/NovaGL/diy-melview

## Installation
Install via HACS, remember to restart Home Assistant after HACS install to allow this integration to be added from Settings/Integrations. 

When prompted, enter your Wi-Fi Control (i.e. app.melview.net) username and password.
Do not tick 'Local' as this functionality is currently not functional.

## License
This project is licensed under the WTF License, as per the original repository.
