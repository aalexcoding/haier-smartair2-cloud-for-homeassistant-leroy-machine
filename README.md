# Haier SmartAir2 for Home Assistant — V3 Cloud Extended

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Custom%20Integration-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Custom%20Repository-41BDF5)](https://hacs.xyz/)
[![HACS validation](https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine/actions/workflows/hacs.yaml/badge.svg)](https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine/actions/workflows/hacs.yaml)
[![hassfest](https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine/actions/workflows/hassfest.yaml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**An unofficial community fork of [bwitosze/haier-smartair2-cloud-for-homeassistant](https://github.com/bwitosze/haier-smartair2-cloud-for-homeassistant), maintained by [Alejandro Delgado (@aalexcoding)](https://github.com/aalexcoding).**

This fork extends the original Home Assistant integration with **Haier SmartAir2 V3 cloud control**, including certain air conditioners equipped with **MK-QTWIFI08 Wi-Fi modules**. The original V2 cloud (EPP over MQTT) and local TCP implementations are retained.

> [!IMPORTANT]
> **Unofficial community integration.** This project is not affiliated with, endorsed by or supported by Haier. It relies on undocumented vendor cloud interfaces that may change at any time.

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

## Requirements

- Home Assistant **2025.1.0** or newer (local brand icons are shown from Home Assistant 2026.3).
- [HACS](https://hacs.xyz/) / the Home Assistant Marketplace, for the recommended installation method.
- An account for the **legacy SmartAir2 app** (not hOn) with your air conditioners already paired in that app.
- Internet access from Home Assistant to the Haier cloud (cloud transports). The local transport needs a compatible module reachable on TCP `56800`.
- Python dependency `paho-mqtt==2.1.0`, installed automatically by Home Assistant.

## Installation

### Marketplace / HACS (recommended)

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=aalexcoding&repository=haier-smartair2-cloud-for-homeassistant-leroy-machine&category=integration)

1. Click the button above, or open the **Marketplace** (HACS) in Home Assistant and search for **Haier SmartAir2 (V3 cloud support)**.
   - The button uses the `marketplace_repository` My Home Assistant redirect introduced in Home Assistant 2026.11; older installations are redirected to HACS.
   - Until this repository is accepted into the default HACS catalog, add it first as a **custom repository** (three-dot menu → **Custom repositories**) with type **Integration**:

     ```text
     https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine
     ```

2. Download the integration.
3. Restart Home Assistant.
4. Continue with [Configuration](#configuration).

> **Already using the upstream integration?** Both projects use the same domain, `haier_smartair2`. Do **not** install both codebases simultaneously. Back up your Home Assistant configuration, replace the installed integration code via HACS, and restart. Do not delete your integration entry or entities unless you intentionally want to reconfigure them.

### Manual installation

1. Download the latest [release](https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine/releases) (or clone this repository).
2. Copy `custom_components/haier_smartair2/` into your Home Assistant `<config>/custom_components/` directory, so that `<config>/custom_components/haier_smartair2/manifest.json` exists.
3. Restart Home Assistant.

Use only one copy of this integration domain.

### Updating

- **HACS / Marketplace:** when a new release is published, Home Assistant shows an update for this integration. Install it and restart Home Assistant.
- **Manual:** replace the whole `custom_components/haier_smartair2/` directory with the one from the new release and restart.
- Read the [CHANGELOG](CHANGELOG.md) before updating. Updates keep your existing config entry and entities; you do not need to remove and re-add the integration.

## Configuration

[![Open your Home Assistant instance and start setting up Haier SmartAir2.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=haier_smartair2)

1. Go to **Settings → Devices & services → Add integration → Haier SmartAir2 (V3 cloud support)** (or use the button above).
2. Enter your **SmartAir2 account** credentials and select the region. Your associated devices will be discovered.

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
- **TLS:** all cloud connections (REST login, gateway discovery and MQTT) verify the server certificate and hostname. This was verified against the European cloud; if the `us` or `sg` gateways present an invalid certificate, connecting fails with a TLS error instead of silently continuing. Please report it if that happens. The **local** transport (TCP `56800`) is plaintext by design of the device protocol.
- **No hOn support:** this project targets older SmartAir2 accounts, not the newer hOn ecosystem or the mainland China cloud API.
- **V2/local regression coverage:** these paths are retained but have not been fully revalidated on a broad hardware selection.

## Reporting issues

Please report bugs and device compatibility results at **[GitHub Issues](https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine/issues)**.

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
