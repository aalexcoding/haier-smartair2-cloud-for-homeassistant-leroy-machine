# Changelog

## 0.2.1

- **Security:** enable TLS certificate and hostname verification for the Haier REST login/device list, gateway discovery (master-gw) and MQTT broker connections, using Home Assistant's shared verified SSL context. Previously verification was disabled (`ssl=False` / `CERT_NONE`). Verified against the European cloud endpoints.
- Add manifest `categories` (`climate.heat_pumps_air_conditioning`) and sort manifest keys as hassfest expects.
- Rename the integration display name to `Haier SmartAir2 (V3 cloud support)` (same as `hacs.json`) to tell it apart from the upstream integration. The `haier_smartair2` domain, entity IDs and existing config entries are unchanged.
- Change the manifest requirement to `paho-mqtt>=2.1.0` (hassfest rejects pinning a package Home Assistant already ships; the installed version is unchanged).
- Remove the undocumented `render_readme` key from `hacs.json`.
- Add HACS and hassfest validation workflows.
- Add an original, generic brand icon in `custom_components/haier_smartair2/brand/` (no Haier trademarks).
- Rewrite README installation, update and issue-reporting sections; replace fork-overlay steps in `README.es.md` with end-user instructions.
- Add `HACS_SUBMISSION.md` with the checklist for `hacs/default`.

## 0.2.0-beta.1 — shipped as GitHub release 0.1.0

- Modular, testable V3 cloud attribute mappings and 32-field `grSetDAC` encoder.
- V3 MQTT power control with two-stage ACK + device-push confirmation.
- Automatic power-on before changes from OFF.
- Fan-only mode transition via LOW fan speed followed by mode 6.
- Independent V3 cloud vertical swing, horizontal swing and purify switches.
- Multiple V3 devices supported by automatic discovery (no device-specific identifiers).
- Serialize each V3 device's multi-step transitions, preserve V2/local paths.
- Remove embedded test-device identifiers and verbose prototype logs.
- Add HACS overlay, publishing helper, pytest suite and CI.

This version was published under the GitHub release tag `0.1.0`, while its manifest declared `0.2.0-beta.1`.
