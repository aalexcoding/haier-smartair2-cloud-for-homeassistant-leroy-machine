# Compatibility matrix — observed vs proposed

| Generation / transport | How identified | Status |
|---|---|---|
| V2 Cloud | Type identifier length <= 32, no local override | Upstream EPP retained; needs regression smoke test |
| V3 Local | Type identifier length > 32, local TCP available | Upstream byte codec retained; needs regression smoke test |
| V3 Cloud (MK-QTWIFI08 family) | Type identifier length > 32, TCP not configured or unavailable | One device verified for all core functions, extras, and power |
| Other V3 Cloud | Type identifier length > 32 | Discovery and command schema available, **not physically verified** |

Feature detection for V3 cloud extras requires incoming attribute names; it is not a guarantee that an actuator moves, or that its semantics are identical across models.

To request support for another V3 device, submit a sanitized report: model, Wi-Fi dongle model, `typeIdentifier` length (not the token), which attribute names are reported, and which physical functions were tested. Do not paste a `User/<access token>/...` topic or entire 32-argument command from your account.
