"""Per-device update coordinator bridging a transport + codec to HA."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .codec import Codec, CodecV3, HaierState
from .v3_cloud import V3_CODE_TO_MODE, V3_CODE_TO_FAN, extra_change, mode_change, fan_change, same_attr
from .const import (
    SCAN_INTERVAL_SECONDS,
    MODE_AUTO, MODE_COOL, MODE_DRY, MODE_HEAT, MODE_FAN,
    FAN_AUTO, FAN_HIGH, FAN_MID, FAN_LOW,
)

_LOGGER = logging.getLogger(__name__)


class HaierCoordinator(DataUpdateCoordinator[HaierState]):
    """Keeps one device's state fresh via periodic poll + async push."""

    def __init__(
        self,
        hass: HomeAssistant,
        transport,
        codec: Codec,
        devid: str,
        name: str,
        via_cloud: bool,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"Haier {name}",
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.transport = transport
        self.codec = codec
        self.devid = devid.upper()
        self.dev_name = name
        self.via_cloud = via_cloud
        self._write_lock = asyncio.Lock()
        # push updates from the transport (device-initiated status frames)
        transport.add_listener(self._on_push)

    def _decode_latest(self) -> HaierState | None:
        frame = self.transport.latest_frame(self.devid)
        state = None

        if frame:
            try:
                state = self.codec.decode(frame)
            except Exception:  # noqa: BLE001
                _LOGGER.debug(
                    "decode failed for %s",
                    self.devid,
                    exc_info=True,
                )

        getter = getattr(self.transport, "latest_attrs", None)
        attrs = getter(self.devid) if getter else {}

        if not attrs:
            return state

        changes = {}

        if "targetTemperature" in attrs:
            try:
                temp = float(attrs["targetTemperature"])
                if 16 <= temp <= 30:
                    changes["target_temp"] = temp
            except (ValueError, TypeError):
                pass

        if "operationMode" in attrs:
            try:
                mode = int(attrs["operationMode"])
                if isinstance(self.codec, CodecV3):
                    if mode in V3_CODE_TO_MODE:
                        changes["mode"] = V3_CODE_TO_MODE[mode]
                elif mode in (0, 1, 2, 3, 4):
                    changes["mode"] = mode
            except (ValueError, TypeError):
                pass

        if "windSpeed" in attrs and isinstance(self.codec, CodecV3):
            try:
                speed = int(attrs["windSpeed"])
                if speed in V3_CODE_TO_FAN:
                    changes["fan"] = V3_CODE_TO_FAN[speed]
            except (ValueError, TypeError):
                pass

        if "indoorTemperature" in attrs:
            try:
                temp = float(attrs["indoorTemperature"])
                if -40 <= temp <= 80:
                    changes["current_temp"] = temp
            except (ValueError, TypeError):
                pass

        if "onOffStatus" in attrs:
            power = str(attrs["onOffStatus"]).strip().lower()
            if power in ("true", "1"):
                changes["power"] = True
            elif power in ("false", "0"):
                changes["power"] = False

        if not changes:
            return state

        return (state or HaierState()).merged(**changes)

    def _on_push(self) -> None:
        state = self._decode_latest()
        if state is not None:
            self.async_set_updated_data(state)
        elif self.is_v3_cloud:
            # boundDevs supplies reachability even before Push/Dev/Attr.
            # Notify HA so it can show an online device with unknown HVAC state.
            self.async_set_updated_data(self.data or HaierState())

    async def _async_update_data(self) -> HaierState:
        if self.is_v3_cloud:
            # V3 Cloud does not answer the legacy EPP status poll. Returning
            # unknown state is preferable to sending useless queries.
            return self._decode_latest() or self.data or HaierState()
        await self.transport.async_poll(self.devid)
        # give the device up to ~2s to answer; the push callback may also fire
        for _ in range(10):
            await asyncio.sleep(0.2)
            state = self._decode_latest()
            if state is not None:
                return state
        return self.data or HaierState()

    @property
    def is_v3_cloud(self) -> bool:
        """V3 cloud uses SDK attribute operations, not EPP frame writes."""
        return self.via_cloud and isinstance(self.codec, CodecV3)

    async def async_extra_trial(self, kind: str, enabled: bool) -> None:
        """V3 cloud extras (per device, only if attributes have been reported)."""
        if not self.is_v3_cloud:
            raise RuntimeError("Additional controls require a V3 cloud device")
        updates = extra_change(kind, enabled)
        async with self._write_lock:
            attrs = self.transport.latest_attrs(self.devid)
            if str(attrs.get("onOffStatus", "")).lower() not in ("true", "1"):
                raise RuntimeError("Device power must be confirmed ON before changing extras")
            # Preserve a fixed louvre position instead of setting it to zero.
            if not enabled and kind in ("swing_vertical", "swing_horizontal"):
                field = next(iter(updates))
                active = "8" if kind == "swing_vertical" else "7"
                if field in attrs and attrs[field] != active:
                    return
            await self.transport.async_write_v3_attrs(self.devid, updates)

    async def async_apply(self, **changes) -> None:
        """Select V3 cloud attribute commands; retain original EPP for V2/local."""
        if self.is_v3_cloud:
            async with self._write_lock:
                await self._async_apply_v3(**changes)
            return

        state = self.data or self._decode_latest() or HaierState()
        if self.via_cloud and len(state.raw_block) < 10:
            raise RuntimeError(
                f"Haier {self.dev_name}: no valid EPP status frame; "
                "refusing potentially destructive write"
            )
        frame = self.codec.encode_set(state, **changes)
        await self.transport.async_send_frame(self.devid, frame)
        await asyncio.sleep(0.6)
        await self.async_request_refresh()

    async def _async_apply_v3(self, **changes) -> None:
        """Serialize the complete transition for one V3 device."""
        keys = set(changes)
        if keys == {"power"}:
            await self.transport.async_write_v3_power(self.devid, bool(changes["power"]))
            return

        if changes.get("power") is not True:
            raise RuntimeError("V3 cloud changes must explicitly request power=True")

        known = self.transport.latest_attrs(self.devid)
        if str(known.get("onOffStatus", "")).lower() not in ("true", "1"):
            # Power uses a single attribute command. It does not need a full
            # attribute snapshot, unlike grSetDAC.
            await self.transport.async_write_v3_power(self.devid, True)

        if keys == {"power", "target_temp"}:
            temp = float(changes["target_temp"])
            if not 16 <= temp <= 30 or not temp.is_integer():
                raise ValueError("V3 temperature must be an integer between 16 and 30")
            await self.transport.async_write_v3_attrs(
                self.devid, {"targetTemperature": str(int(temp))}
            )
        elif keys == {"power", "mode"}:
            mode = changes["mode"]
            update = mode_change(mode)
            attrs = self.transport.latest_attrs(self.devid)
            if mode == MODE_FAN and not same_attr(
                "operationMode", attrs.get("operationMode"), update["operationMode"]
            ):
                # In live tests heat+auto fan -> fan_only was rejected errNo=12.
                # SmartAir2 switched to LOW (3) before changing to fan_only (6).
                # Keep separate ACK+push-confirmed writes.
                await self.transport.async_write_v3_attrs(
                    self.devid, fan_change(FAN_LOW)
                )
            await self.transport.async_write_v3_attrs(self.devid, update)
        elif keys == {"power", "fan", "quiet", "turbo"}:
            if changes["quiet"] or changes["turbo"]:
                raise RuntimeError("Quiet/Turbo not verified for V3 cloud")
            await self.transport.async_write_v3_attrs(
                self.devid, fan_change(changes["fan"])
            )
        else:
            raise RuntimeError(f"Unsupported V3 cloud operation: {sorted(keys)}")
