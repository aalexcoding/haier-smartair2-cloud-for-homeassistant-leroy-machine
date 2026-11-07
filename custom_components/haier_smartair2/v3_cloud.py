"""Pure SmartAir2 cloud V3 attribute protocol helpers.

No Home Assistant or MQTT dependencies. Based on tested SmartAir2 uSDK V3
attribute reports and the grSetDAC operation; more profiles may differ.
"""

from __future__ import annotations

# The ordering is significant: grSetDAC uses the 32 arguments defined by the V3 SDK.
V3_ARGUMENTS: tuple[str, ...] = (
    "targetTemperature", "windDirectionVertical", "operationMode",
    "specialMode", "windSpeed", "energySavePeriod", "tempUnit",
    "pmvStatus", "intelligenceStatus", "halfDegreeSettingStatus",
    "screenDisplayStatus", "10degreeHeatingStatus", "echoStatus",
    "lockStatus", "silentSleepStatus", "muteStatus", "rapidMode",
    "electricHeatingStatus", "healthMode", "onOffStatus",
    "targetHumidity", "humanSensingStatus", "windDirectionHorizontal",
    "cloudFilterChangeFlag", "cleaningTimeStatus", "energySavingStatus",
    "lightStatus", "selfCleaningStatus", "ch2oCleaningStatus",
    "pm2p5CleaningStatus", "humidificationStatus", "freshAirStatus",
)

# The SDK supplies these when omitted by some attribute snapshots. Do not
# assume defaults for any other argument: a missing state blocks grSetDAC.
V3_OPTIONAL_DEFAULTS = {
    "cloudFilterChangeFlag": "false",
    "cleaningTimeStatus": "false",
}

# Internal normalized HaierState mode / fan -> V3 cloud values.
V3_MODE_TO_CODE = {0: "0", 1: "1", 4: "2", 2: "4", 3: "6"}
V3_CODE_TO_MODE = {int(raw): mode for mode, raw in V3_MODE_TO_CODE.items()}
V3_FAN_TO_CODE = {0: "1", 1: "2", 2: "3", 3: "5"}
V3_CODE_TO_FAN = {int(raw): fan for fan, raw in V3_FAN_TO_CODE.items()}

V3_EXTRA_UPDATES = {
    "swing_vertical": ("windDirectionVertical", "8", "0"),
    "swing_horizontal": ("windDirectionHorizontal", "7", "0"),
}
V3_PURIFY_FIELDS = ("healthMode", "pm2p5CleaningStatus", "ch2oCleaningStatus")


def normalized(value: object) -> str:
    """Normalize status booleans without affecting numerics/unknown fields."""
    value = str(value).strip()
    if value.lower() in ("true", "false"):
        return value.lower()
    return value


def same_attr(name: str, old: object, new: object) -> bool:
    """Compare wire values, preserving 24 == 24.00 for setpoints."""
    if old is None:
        return False
    if name == "targetTemperature":
        try:
            return abs(float(old) - float(new)) < 0.01
        except (ValueError, TypeError):
            return False
    return normalized(old) == normalized(new)


def attrs_match(attrs: dict[str, str], changes: dict[str, str]) -> bool:
    return all(same_attr(k, attrs.get(k), v) for k, v in changes.items())


def make_grsetdac_args(attrs: dict[str, str], changes: dict[str, str]) -> list[dict[str, str]]:
    """Construct complete 32-field V3 SDK command. Never guess unknown values."""
    if not changes or any(k not in V3_ARGUMENTS for k in changes):
        raise ValueError("Unknown or missing V3 attribute change")
    missing = [k for k in V3_ARGUMENTS if k not in attrs and k not in V3_OPTIONAL_DEFAULTS and k not in changes]
    if missing:
        raise ValueError(f"Missing V3 device attributes: {', '.join(missing)}")
    return [
        {k: normalized(changes[k] if k in changes else attrs.get(k, V3_OPTIONAL_DEFAULTS.get(k)))}
        for k in V3_ARGUMENTS
    ]


def mode_change(mode: int) -> dict[str, str]:
    return {"operationMode": V3_MODE_TO_CODE[mode]}


def fan_change(fan: int) -> dict[str, str]:
    return {"windSpeed": V3_FAN_TO_CODE[fan]}


def extra_change(kind: str, enabled: bool) -> dict[str, str]:
    if kind == "purify":
        value = "true" if enabled else "false"
        return dict.fromkeys(V3_PURIFY_FIELDS, value)
    field, on, off = V3_EXTRA_UPDATES[kind]
    return {field: on if enabled else off}
