# Changelog

## Unreleased

- Fall back to port 443 for the Haier REST API (login and device list) when the usual port 7263 refuses connections, and remember whichever port answered. In November 2026, port 7263 started refusing connections while the same API kept answering on 443. That broke setup (`Haier device list failed: Cannot connect to host uhome.haieriot.net:7263`) and every cloud reconnect.
- Fix commands failing with `Haier MQTT not connected` while the entity still looked available. The device now shows as unavailable once the cloud has been unreachable for more than 60 seconds. Short reconnects, such as the token refresh, do not affect it.
- A command sent while disconnected skips the back-off wait, reconnects at once and waits up to 15 seconds instead of failing straight away. Commands cannot start a new login more than once every 15 seconds.
- Treat the cloud session as ready only after the broker confirms the reply subscriptions (SUBACK, or a 5-second fallback). This prevents commands from losing their ACK right after a reconnect.
- Reset the reconnect back-off only once a session works. A broker that accepts the socket but refuses or drops the session no longer causes a login every few seconds.
- Limit login to 20 seconds and a whole connection attempt to 60 seconds. A 60-second watchdog restarts a reconnect that is stuck and reconnects a session that is dead with no retry pending. A failed attempt no longer leaves a half-open client behind.
- Gateway discovery no longer loops forever at 100% CPU if the gateway closes the socket mid-reply. Before, that blocked every later reconnect.
- Malformed cloud messages can no longer kill the MQTT network thread.
- Start reauthentication only after three login rejections in a row. Haier also rejects logins during rate limiting or maintenance. Initial setup still asks for the password on the first rejection.

## 0.2.2

- Stop automatic cloud login attempts after an authentication failure and start Home Assistant reauthentication. Setup authentication failures now raise `ConfigEntryAuthFailed`.
- Add a password confirmation flow that validates the replacement password, preserves the existing account and configuration, and reloads the entry. Add English and Polish prompts.
- Retry connection failures with exponential backoff (30, 60, 120, 240, then 300 seconds), reset after success, and cancel pending retries and token refreshes on authentication failure or unload.
- Reload options explicitly to avoid duplicate reloads during reauthentication while retaining Home Assistant 2025.1 compatibility.
- Add regression tests for authentication failures, reauthentication, reconnect backoff and shutdown.

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
