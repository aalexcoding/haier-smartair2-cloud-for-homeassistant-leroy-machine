# Haier SmartAir2 — Cloud V3 extension for Home Assistant

[Versión en español](README.es.md)

**Unofficial community fork** of [bwitosze/haier-smartair2-cloud-for-homeassistant](https://github.com/bwitosze/haier-smartair2-cloud-for-homeassistant).

Adds Haier SmartAir2 **V3 cloud attribute control** while preserving the original V2 cloud EPP and local TCP paths. **Not hOn.** This integration uses your own SmartAir2 account and the manufacturer's cloud MQTT connection. It is not affiliated with Haier.

> **Beta:** V3 commands and the `MK-QTWIFI08` family were confirmed with one physical unit. Other V3 devices and clean-install behavior have automated coverage but require independent hardware testing. Do not advertise broad model compatibility as proven.

## Supported functions

| Feature | V3 cloud (observed) | V2 cloud / local |
| --- | --- | --- |
| Temperature and operating modes | MQTT `grSetDAC` | Original EPP / LAN code |
| Fan speeds | Auto / low / medium / high | Original behavior |
| Power | MQTT single attribute `Req/Attr/W` | Original behavior |
| Fan only | Set fan LOW then switch mode 6, confirmed in sequence | Original behavior |
| Up/down swing | Separate `switch`, `8`/`0` | Original native swing when supported |
| Left/right swing | Separate `switch`, `7`/`0` | Original behavior |
| Purify | Switch, updates 3 flags together | Original behavior |

The V3 switch entities are created for every cloud V3 device, **but remain unavailable unless the device reports the corresponding attributes**. Some models may not implement all the physical features. Changes require a complete 32-attribute read snapshot and are not sent blindly.

## Installation with HACS

1. Fork the [upstream repository](https://github.com/bwitosze/haier-smartair2-cloud-for-homeassistant/fork) on GitHub, keeping its history and **LICENSE**.
2. Apply this overlay to the **root** of your fork and run `python scripts/configure_fork.py --github-user YOUR_USERNAME`.
3. Commit and push, create a pre-release when tested. Until then use your default branch.
4. In HACS → three-dot menu → **Custom repositories**, paste `https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant`, category **Integration**.
5. Install, restart Home Assistant, then add **Haier SmartAir2** under Settings → Devices & Services. Log in using your SmartAir2 account and select the region.
6. All devices returned by the account are discovered automatically. For local plaintext modules, optionally configure the `MAC:IP` mapping in Options.

For manual installation, copy `custom_components/haier_smartair2` into `<config>/custom_components/` and restart Home Assistant.

**Do not install the upstream and the fork simultaneously:** both use the `haier_smartair2` integration domain. When upgrading an existing installation, back it up first. Current entity unique IDs and device IDs are preserved.

## How V3 writes work

- REST login → Haier gateway → MQTT subscription to cloud device attribute pushes.
- `onOffStatus` is written individually and confirmed by `Resp/Attr/W` and a matching `Push/Dev/Attr`.
- Other V3 controls send a **32-argument** `grSetDAC` command; unknown attributes are never invented (two observed optional default flags excepted).
- Commands are serialized per device and correlate their acknowledgment with both the device ID and sequence number. `errNo=0` is necessary but **not sufficient**: matching device state must also arrive.
- Switching to `fan_only` normalizes fan speed to LOW first, as required in the tested heat → fan transition. An error aborts the sequence.
- Changes from `OFF` power on before changing the HVAC mode. A missing read snapshot blocks group writes, not power toggles.

## Known limitations

- **Initial V3 attributes**: EPP polling does not reliably return V3 cloud status. The integration currently waits for a `Push/Dev/Attr` message before enabling group commands. This can delay controls after a restart until the app/device emits a status event. There is no invented "state refresh" endpoint.
- **Other V3 models**: operation codes and optional features can differ. See [COMPATIBILITY.md](COMPATIBILITY.md) before contributing reports.
- Original cloud handshake and REST login currently use relaxed TLS verification inherited from the upstream protocol implementation; this is a security limitation pending compatibility testing. Use only on networks you trust.
- New HACS installations are **not yet verified against an external HA instance**. Unit tests do not replace end-to-end tests.
- Not compatible with the hOn app or the China cloud API.

## Developing and contributing

Run `python -m pytest -q` for pure protocol tests. See [DEVELOPMENT.md](DEVELOPMENT.md) and [CHANGELOG.md](CHANGELOG.md).

Please remove access tokens, passwords, IP addresses, device IDs and complete MQTT payloads before reporting issues. Use issue templates describing `typeIdentifier` **length**, firmware / app, attributes present and results, not credentials.

## Credits and license

Based on the MIT-licensed integration by **bwitosze**, and earlier reverse engineering by Piotr Stadnicki (fastfend/HaierACBridge), ESPHome Haier and the HaierProtocol community. The **upstream `LICENSE` must remain in your fork**; this overlay does not replace it.

Unofficial project. Not endorsed by Haier; proprietary cloud behavior may change without notice.
