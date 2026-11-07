# Changelog

## 0.2.0-beta.1 — candidate, not published

- Modular, testable V3 cloud attribute mappings and 32-field `grSetDAC` encoder.
- V3 MQTT power control with two-stage ACK + device-push confirmation.
- Automatic power-on before changes from OFF.
- Fan-only mode transition via LOW fan speed followed by mode 6.
- Independent V3 cloud vertical swing, horizontal swing and purify switches.
- Multiple V3 devices supported by automatic discovery (no device-specific identifiers).
- Serialize each V3 device's multi-step transitions, preserve V2/local paths.
- Remove embedded test-device identifiers and verbose prototype logs.
- Add HACS overlay, publishing helper, pytest suite and CI.

This release has **not** been validated on a separate clean Home Assistant installation.
