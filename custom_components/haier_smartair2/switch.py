"""Optional V3 cloud controls; entities appear for every discovered V3 unit."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import HaierConfigEntry
from .const import DOMAIN
from .coordinator import HaierCoordinator

_CONTROLS = (
    ("swing_vertical", "Vertical swing"),
    ("swing_horizontal", "Horizontal swing"),
    ("purify", "Purify"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: HaierConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entities = []
    for coord in entry.runtime_data.coordinators:
        if coord.is_v3_cloud:
            entities.extend(HaierExtraSwitch(coord, kind, name) for kind, name in _CONTROLS)
    async_add_entities(entities)


class HaierExtraSwitch(CoordinatorEntity[HaierCoordinator], SwitchEntity):
    """Independent on/off switches; preserves fixed louvre positions when possible."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: HaierCoordinator, kind: str, name: str) -> None:
        super().__init__(coordinator)
        self._kind = kind
        self._attr_unique_id = f"{DOMAIN}_{coordinator.devid}_{kind}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, coordinator.devid)})

    def _attrs(self) -> dict[str, str]:
        getter = getattr(self.coordinator.transport, "latest_attrs", None)
        return getter(self.coordinator.devid) if getter else {}

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        if self.coordinator.is_v3_cloud:
            # An absent state snapshot is unknown, not a disconnected device.
            # A write still requires the complete snapshot in grSetDAC.
            return self.coordinator.transport.is_online(self.coordinator.devid)
        if self.coordinator.data is None:
            return False
        attrs = self._attrs()
        if self._kind == "swing_vertical":
            return "windDirectionVertical" in attrs
        if self._kind == "swing_horizontal":
            return "windDirectionHorizontal" in attrs
        return all(k in attrs for k in (
            "healthMode", "pm2p5CleaningStatus", "ch2oCleaningStatus",
        ))

    @property
    def is_on(self) -> bool | None:
        attrs = self._attrs()
        if self._kind == "swing_vertical":
            val = attrs.get("windDirectionVertical")
            return None if val is None else val == "8"
        if self._kind == "swing_horizontal":
            val = attrs.get("windDirectionHorizontal")
            return None if val is None else val == "7"
        keys = ("healthMode", "pm2p5CleaningStatus", "ch2oCleaningStatus")
        values = [str(attrs.get(k, "")).lower() for k in keys]
        if all(v == "true" for v in values):
            return True
        if all(v == "false" for v in values):
            return False
        return None

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_extra_trial(self._kind, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_extra_trial(self._kind, False)
