# Haier SmartAir2 for Home Assistant — V3 Cloud Extended

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Custom%20Integration-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Custom%20Repository-41BDF5)](https://hacs.xyz/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**An unofficial community fork of [bwitosze/haier-smartair2-cloud-for-homeassistant](https://github.com/bwitosze/haier-smartair2-cloud-for-homeassistant), maintained by [Alejandro Delgado (@aalexcoding)](https://github.com/aalexcoding).**

This fork extends the original Home Assistant integration with **Haier SmartAir2 V3 cloud control**, including certain air conditioners equipped with **MK-QTWIFI08 Wi-Fi modules**. The original V2 cloud (EPP over MQTT) and local TCP implementations are retained.

**This is for the legacy SmartAir2 app, not Haier hOn.** No Android bridge or vendor SDK is required at runtime. Cloud devices require an active SmartAir2 account and internet connectivity.

> **Beta / community project.** V3 cloud controls have been tested on MK-QTWIFI08 hardware. Not every V3 model has been verified; V2 cloud and local operation retain upstream code but still need regression testing with additional physical devices.

## Features

- Native Home Assistant `climate` entity and indoor temperature sensor per unit.
- Automatic discovery of devices linked to your SmartAir2 account.
- Original transports retained: **V2 Cloud** (MQTT + EPP) and **Local** (TCP port `56800`, where supported).
- **V3 Cloud:** power on/off, target temperature, `auto`, `cool`, `heat`, `dry`, `fan_only`, and `auto / low / medium / high` fan speeds.
- **Three additional V3 Cloud switches** per device when applicable: vertical swing, horizontal swing, and **Purify**.
- Independent per-device MQTT commands, serialized operations, server acknowledgements and state-change confirmation.
- Connected V3 devices can report an **unknown initial HVAC state** instead of being marked unavailable merely because no attribute snapshot has arrived.
- Spanish documentation: **[README.es.md](README.es.md)**.

## Compatibility

| Device generation / transport | Status | Notes |
| --- | --- | --- |
| V2 Cloud | Original support retained | EPP protocol over Haier MQTT; regression testing on V2 hardware is welcome. |
| V3 Local | Original experimental support retained | Direct TCP `56800` on compatible plaintext modules; not all V3 dongles support it. |
| V3 Cloud — MK-QTWIFI08 | **Tested on real hardware** | Full climate controls, swings and Purify tested on one unit; four devices discovered and additional multi-device behavior exercised. |
| Other V3 Cloud devices | **Experimental** | Compatible attributes and command support vary by model; please report results. |

The integration chooses a transport per device based on the existing configuration. V3 cloud compatibility is not a guarantee that every air conditioner supports every physical feature.

### V3 cloud-specific controls

| Function | Implementation |
| --- | --- |
| Power | Single MQTT attribute write to `onOffStatus`. |
| Target temperature | V3 `grSetDAC` operation; tested range: **16–30 °C, whole degrees**. |
| HVAC mode | V3 `grSetDAC` operation. |
| Fan only | Set fan to LOW first, then enter fan-only mode, with a confirmation after each step. |
| Vertical swing | Separate `switch` using `windDirectionVertical`. |
| Horizontal swing | Separate `switch` using `windDirectionHorizontal`. |
| Purify | Separate `switch` updating `healthMode`, `pm2p5CleaningStatus`, and `ch2oCleaningStatus` together. |

The extra switches are separate Home Assistant entities; they do **not** automatically appear inside the default thermostat popup. Add them to an Entities card if desired.

## Installation

### HACS (recommended)

1. Open **HACS → Custom repositories** in Home Assistant.
2. Add this repository as category **Integration**:

   ```text
   https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine
   ```

3. Find **Haier SmartAir2 (V3 cloud support)** and download it.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration → Haier SmartAir2**.
6. Enter your **SmartAir2 account** credentials and select the region. Your associated devices will be discovered.

> **Already using the upstream integration?** Both projects use the same domain, `haier_smartair2`. Do **not** install both codebases simultaneously. Back up your Home Assistant configuration, replace the installed integration code via HACS, and restart. Do not delete your integration entry or entities unless you intentionally want to reconfigure them.

### Manual installation

Copy `custom_components/haier_smartair2/` from this repository to your Home Assistant `<config>/custom_components/` directory, then restart Home Assistant. Use only one copy of this integration domain.

## Configuration

The configuration flow supports:

- **Email and password** for the old SmartAir2 app (not hOn).
- **Region** for the Haier cloud gateway. European cloud has been tested; other regions are not guaranteed.
- Optional **local device mappings** (`MAC:IP`) for compatible devices, using the original local transport.

You can change region and local mappings later in the integration options. Changing the transport may affect entity IDs, so review dashboards and automations afterward.

## How V3 cloud control works

The V3 cloud implementation builds on the original SmartAir2 authentication and MQTT connection:

1. Authenticate with the Haier SmartAir2 cloud and discover associated devices.
2. Subscribe to MQTT device events, including `Push/Dev/Attr`.
3. Use a single-attribute write for power, or a complete `grSetDAC` operation for other V3 settings.
4. Verify both the gateway response (`errNo=0`) **and** the expected device-attribute update.
5. Serialize commands per device and preserve unrelated settings when generating full V3 operations.

A full `grSetDAC` operation needs the device's existing attribute snapshot. **If required attributes are missing, the integration blocks that group write rather than guessing values.** Power commands use a separate path and do not need the full snapshot.

### State after restart

A V3 cloud device reported online by Haier can be shown as available with an **unknown** mode or temperature until its first `Push/Dev/Attr` arrives. Basic power control can still be requested. Mode, temperature, fan, swing and Purify writes may need the complete snapshot and can be rejected safely until one arrives.

**Automatic read-only V3 state refresh is not implemented yet.** The integration does not send an automatic `turn_off` just to obtain state, since that could switch off an air conditioner that was already operating.

## Limitations and security

- **Beta compatibility:** MK-QTWIFI08 is the principal tested V3 cloud family. Please do not assume support for all V3 units or every optional capability.
- **Cloud dependency:** V3 cloud requires the vendor service; protocol/server changes can affect functionality.
- **Initial attributes:** after restart, some values can remain unknown until Haier emits an attribute push.
- **Legacy TLS behavior:** parts of the inherited cloud handshake disable certificate verification. This is a known security limitation under review; do not treat this as a security-hardened integration.
- **No hOn support:** this project targets older SmartAir2 accounts, not the newer hOn ecosystem or the mainland China cloud API.
- **V2/local regression coverage:** these paths are retained but have not been fully revalidated on a broad hardware selection.

## Development and contributions

Contributions, device reports and pull requests are welcome. Before opening an issue, please provide your AC model, Wi-Fi module, integration version, Home Assistant version, region and a description of the expected versus actual behavior.

**Never publish** SmartAir2 credentials, access tokens, complete MQTT topics containing tokens, or unredacted device identifiers.

For development:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q custom_components/haier_smartair2
```

See [COMPATIBILITY.md](COMPATIBILITY.md), [CHANGELOG.md](CHANGELOG.md), and [DEVELOPMENT.md](DEVELOPMENT.md).

## Authors, credits and acknowledgements

This project exists thanks to the efforts of several open-source contributors:

- **Original Home Assistant integration — [bwitosze](https://github.com/bwitosze):** creator of [haier-smartair2-cloud-for-homeassistant](https://github.com/bwitosze/haier-smartair2-cloud-for-homeassistant), which provides the foundation, SmartAir2 cloud integration, V2 EPP handling and local transport.
- **V3 Cloud extension and fork maintenance — [Alejandro Delgado (@aalexcoding)](https://github.com/aalexcoding):** extended the integration for MK-QTWIFI08 / V3 cloud devices, including MQTT attribute operations, additional swing and Purify controls, multi-device handling, fan-only transitions and unknown-initial-state handling, backed by real-device testing.
- **Previous protocol research — [Piotr Stadnicki (@fastfend)](https://github.com/fastfend):** [HaierACBridge](https://github.com/fastfend/HaierACBridge) and earlier SmartAir2 reverse-engineering work used as technical references.
- **Protocol documentation and community research — [paveldn/HaierProtocol](https://github.com/paveldn/HaierProtocol) and [ESPHome Haier](https://esphome.io/components/climate/haier/).**

Special thanks to the Home Assistant and open-source communities. The credits to the original author are preserved intentionally: **this is a fork, not a replacement for the authorship of the original project.**

## License

Distributed under the **[MIT License](LICENSE)** of the original project. The original license notice must be retained in derived copies and distributions.

## Disclaimer

This project is unofficial, not affiliated with or endorsed by Haier, and uses undocumented proprietary cloud interfaces. Use it at your own risk. All product names and trademarks belong to their respective owners.
