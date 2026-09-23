# ha-denonavr

Home Assistant's built-in Denon AVR integration (`denonavr`), with the receiver's
settings added as entities. It installs as a custom integration under the same
domain, so it takes over the existing config entry and `media_player` entity.

## What it adds

With telnet on (Configure, "Use telnet"), the main zone gets these entities on
the receiver's device. They follow the receiver's telnet events, so a change made
on the remote or in the receiver's menu shows straight away.

| Entity | Type | Range or options |
| --- | --- | --- |
| Bass, Treble | number | -6 to +6 dB |
| Audio delay | number | 0 to 200 ms |
| Dynamic Volume | select | Off, Light, Medium, Heavy |
| MultEQ | select | as the receiver reports |
| Reference level offset | select | 0, +5, +10, +15 dB |
| Dynamic EQ | switch | |

Without telnet nothing would keep them current, so none are created.

## Volume fix

With telnet on, the library sends the main zone's volume as whole dB and drops
a half step, so -30.5 dB lands at -31. `volume.py` sends the receiver's
three-digit form (`MV495`) for the main zone. Other zones, and setups without
telnet, use the library as it is.

## Keeping up with core

`main` starts from a verbatim copy of `homeassistant/components/denonavr` at the
Home Assistant release named in the first commit. The additions live in
`entity.py`, `number.py`, `select.py`, `switch.py`, `volume.py` and `translations/`,
plus the platform list in `__init__.py`, the volume call in `media_player.py` and
the version in `manifest.json`. To take a new
core release, copy its `denonavr` directory over, restore those, and move
`requirements_test.txt` to the matching `pytest-homeassistant-custom-component`.
