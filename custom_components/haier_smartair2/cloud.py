"""Cloud transport: persistent MQTT connection to the Haier uSDK gateway.

Reproduces the uSDK gateway handshake reverse-engineered from liball-in-one.so:
login -> master-gw request -> MQTT 3.1 CONNECT with AES-signed credentials ->
boundDevs registration -> EPP frames over ``User/<token>/Ext/{Req,Push}/<devId>``.

One client multiplexes all cloud devices on a single long-lived connection, like
the app. The access token is a short-lived TGT ticket, refreshed periodically and
on ``invalidToken`` by a full reconnect (topics embed the token).

V3 devices use the cloud attribute protocol for writes. Cloud V2 and
local transports retain the original EPP frame path.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import socket
import ssl
import struct
from collections.abc import Callable

import paho.mqtt.client as mqtt
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .v3_cloud import attrs_match, make_grsetdac_args, normalized, same_attr

from .const import (
    APP_ID,
    APP_KEY,
    APP_VERSION,
    AUTH_SALT,
    LOGIN_HOST,
    LOGIN_PORT,
    MASTER_GW_PORT,
    REST_CLIENT_ID,
    TOKEN_REFRESH_SECONDS,
    generate_client_id,
)

_LOGGER = logging.getLogger(__name__)


def _insecure_ctx() -> ssl.SSLContext:
    # bare context: create_default_context() loads the CA store from disk, which is a
    # blocking call in the event loop - and verification is disabled here anyway
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _make_auth() -> tuple[str, str]:
    """username = '01'+8-digit nonce, password = hex(AES128CBC(MD5(nonce), '<len>haier_sdk')).

    Recipe from uss_encrpyt_user_auth / uss_encrpyt_aes128.
    """
    nonce = ""
    while len(nonce) < 8:
        nonce += str(os.urandom(1)[0])
    nonce = nonce[:8]
    key = hashlib.md5(nonce.encode()).digest()
    pt = bytearray(16)
    struct.pack_into(">H", pt, 0, len(AUTH_SALT))
    pt[2 : 2 + len(AUTH_SALT)] = AUTH_SALT
    enc = Cipher(algorithms.AES(key), modes.CBC(b"\x00" * 16)).encryptor()
    ct = enc.update(bytes(pt)) + enc.finalize()
    return "01" + nonce, ct.hex()


class HaierCloudClient:
    """Single persistent MQTT connection multiplexing all cloud devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        gateway: str,
        app_client_id: str | None = None,
    ) -> None:
        self._hass = hass
        self._username = username
        self._password = password
        self._gateway = gateway
        self._app_client_id = app_client_id or generate_client_id()
        self._token: str | None = None
        self._client: mqtt.Client | None = None
        self._broker_port: int | None = None
        self._devices: set[str] = set()
        self._frames: dict[str, bytes] = {}
        self._attrs: dict[str, dict[str, str]] = {}
        self._online: dict[str, bool] = {}
        self._listeners: list[Callable[[], None]] = []
        self._sn = 100
        self._control_locks: dict[str, asyncio.Lock] = {}
        self._pending_op_responses: dict[tuple[str, str], asyncio.Future] = {}
        self._pending_attr_responses: dict[tuple[str, str], asyncio.Future] = {}
        self._lock = asyncio.Lock()
        self._reconnecting = False
        self._stopped = False
        self._refresh_unsub: asyncio.TimerHandle | None = None

    # ------------------------------------------------------------------ debug

    def _mask(self, text: str) -> str:
        """Hide the access token in anything we log."""
        if self._token:
            text = text.replace(self._token, "<token>")
        return text

    # -------------------------------------------------------------- registration

    def register_device(self, devid: str) -> None:
        self._devices.add(devid.upper())

    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)

        def remove() -> None:
            if cb in self._listeners:
                self._listeners.remove(cb)

        return remove

    def latest_attrs(self, devid: str) -> dict[str, str]:
        return dict(self._attrs.get(devid.upper(), {}))

    def latest_frame(self, devid: str) -> bytes | None:
        return self._frames.get(devid.upper())

    def is_online(self, devid: str) -> bool:
        return self._online.get(devid.upper(), False)

    def _notify(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("listener failed")

    # --------------------------------------------------------------------- REST

    async def async_login(self) -> str:
        session = async_get_clientsession(self._hass)
        body = {
            "loginId": self._username,
            "password": self._password,
            "accType": 0,
            "loginType": 2,
            "sequenceId": "20260101000000000000",
        }
        headers = {
            "appKey": APP_KEY,
            "appId": APP_ID,
            "appVersion": APP_VERSION,
            "clientId": REST_CLIENT_ID,
            "Content-Type": "application/json;charset=utf-8",
            "Accept": "application/json",
        }
        url = f"https://{LOGIN_HOST}:{LOGIN_PORT}/uhome/acbiz/login"
        async with session.post(url, data=json.dumps(body), headers=headers, ssl=False) as resp:
            data = await resp.json(content_type=None)
        _LOGGER.debug("Haier login returned retCode=%s", data.get("retCode"))
        if data.get("retCode") != "00000" or not data.get("accessToken"):
            raise CloudAuthError(f"login failed: {data.get('retCode')} {data.get('retInfo')}")
        self._token = data["accessToken"]
        return self._token

    async def async_get_devices(self) -> list[dict]:
        """Return [{id, name, type}] from get_userDevlist."""
        if not self._token:
            await self.async_login()
        session = async_get_clientsession(self._hass)
        headers = {
            "appKey": APP_KEY,
            "appId": APP_ID,
            "appVersion": APP_VERSION,
            "clientId": REST_CLIENT_ID,
            "accessToken": self._token,
            "Content-Type": "application/json;charset=utf-8",
            "Accept": "application/json",
        }
        body = {"get_devlist_info": {"sctx": {"appId": APP_ID, "appVersion": APP_VERSION, "clientId": REST_CLIENT_ID}}}
        url = f"https://{LOGIN_HOST}:{LOGIN_PORT}/uhome/acbiz/device/v25/get_userDevlist"
        async with session.post(url, data=json.dumps(body), headers=headers, ssl=False) as resp:
            data = await resp.json(content_type=None)
        out: list[dict] = []
        for city in data.get("cityListResult") or []:
            for room in city.get("roomDeviceResultList") or []:
                for d in room.get("deviceList") or []:
                    out.append(
                        {
                            "id": d.get("id"),
                            "name": d.get("name") or d.get("id"),
                            "type": (d.get("type") or {}).get("typeIdentifier"),
                            "online": (d.get("status") or {}).get("online"),
                        }
                    )
        for dev in out:
            _LOGGER.debug(
                "DBG device: id=%s name=%s type=%s (len %s) online=%s",
                dev["id"],
                dev["name"],
                dev["type"],
                len(dev["type"] or ""),
                dev["online"],
            )
        return out

    def _master_gw_blocking(self) -> int:
        j = json.dumps(
            {
                "protocolVers": "1.0.0",
                "clientId": self._app_client_id,
                "connType": "MqttUSdk",
                "svcVers": "0.0.0",
                "libVers": "0.0.0",
                "userAGpType": "UCP-MQTT-UACP",
                "userAGpVers": "1.2.0",
            }
        ).encode()
        hdr = bytearray(8)
        hdr[1] = 1
        struct.pack_into(">H", hdr, 2, 1)
        struct.pack_into(">H", hdr, 6, len(j))
        with socket.create_connection((self._gateway, MASTER_GW_PORT), timeout=8) as s:
            with _insecure_ctx().wrap_socket(s, server_hostname=self._gateway) as ss:
                ss.sendall(bytes(hdr) + j)
                data = b""
                while len(data) < 8:
                    data += ss.recv(4096)
                ln = struct.unpack(">H", data[6:8])[0]
                while len(data) < 8 + ln:
                    data += ss.recv(4096)
                reply = json.loads(data[8 : 8 + ln])
                _LOGGER.debug("Haier gateway discovery succeeded")
                return reply["port"]

    # ------------------------------------------------------------------- start

    async def async_start(self) -> None:
        await self._connect()
        self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        if self._refresh_unsub is not None:
            self._refresh_unsub.cancel()
            self._refresh_unsub = None
        if self._stopped:
            return
        loop = self._hass.loop
        self._refresh_unsub = loop.call_later(
            TOKEN_REFRESH_SECONDS,
            lambda: self._hass.async_create_background_task(self._reconnect("token refresh"), "haier_cloud_reconnect"),
        )

    async def _connect(self) -> None:
        async with self._lock:
            await self.async_login()
            self._broker_port = await self._hass.async_add_executor_job(self._master_gw_blocking)
            username, password = _make_auth()
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id="HA" + os.urandom(8).hex().upper(),
                protocol=mqtt.MQTTv31,
            )
            client.username_pw_set(username, password)
            client.tls_set_context(_insecure_ctx())
            client.on_connect = self._on_connect
            client.on_message = self._on_message
            client.on_disconnect = self._on_disconnect
            client.on_subscribe = self._on_subscribe
            self._client = client
            _LOGGER.debug(
                "DBG MQTT connecting to %s:%s (devices: %s)",
                self._gateway,
                self._broker_port,
                sorted(self._devices),
            )
            await self._hass.async_add_executor_job(
                client.connect, self._gateway, self._broker_port, 30
            )
            client.loop_start()

    async def _reconnect(self, reason: str) -> None:
        if self._stopped or self._reconnecting:
            return
        self._reconnecting = True
        _LOGGER.info("Haier cloud reconnect: %s", reason)
        try:
            if self._client:
                try:
                    self._client.loop_stop()
                    self._client.disconnect()
                except Exception:  # noqa: BLE001
                    pass
            await asyncio.sleep(2)
            await self._connect()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("reconnect failed; retrying in 30s")
            self._hass.loop.call_later(
                30, lambda: self._hass.async_create_background_task(self._reconnect("retry"), "haier_cloud_reconnect")
            )
        finally:
            self._reconnecting = False
            self._schedule_refresh()

    # --------------------------------------------------------------- callbacks

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        _LOGGER.debug("DBG MQTT CONNACK rc=%s", reason_code)
        if getattr(reason_code, "value", reason_code) != 0:
            _LOGGER.warning("Haier cloud CONNACK rc=%s", reason_code)
            return
        token = self._token
        client.subscribe(
            [(f"Client/{self._app_client_id}/Business/Down", 0), (f"User/{token}/#", 0)]
        )
        self._sn += 1
        data = base64.b64encode(json.dumps({"sn": str(self._sn)}).encode()).decode()
        info = client.publish(
            f"Client/{self._app_client_id}/Business/Up",
            json.dumps({"type": "boundDevs", "data": data, "tokens": [token]}),
        )
        _LOGGER.debug("DBG boundDevs request sent rc=%s", info.rc)
        # kick a status poll for every managed device
        from .codec import POLL_FRAME

        for devid in self._devices:
            self._publish_epp(devid, POLL_FRAME)

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties=None) -> None:
        _LOGGER.debug("DBG MQTT SUBACK mid=%s codes=%s", mid, reason_codes)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if self._stopped:
            return
        _LOGGER.info("Haier cloud disconnected rc=%s", reason_code)
        self._hass.loop.call_soon_threadsafe(
            lambda: self._hass.async_create_background_task(self._reconnect("disconnect"), "haier_cloud_reconnect")
        )

    def _on_message(self, client, userdata, msg) -> None:
        _LOGGER.debug("SmartAir2 MQTT message received on %s", self._mask(msg.topic))
        try:
            payload = json.loads(msg.payload)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("MQTT message is not JSON")
            return
        if not isinstance(payload, dict):
            return
        if "/Resp/Attr/W/" in msg.topic and isinstance(payload, dict):
            devid = msg.topic.rsplit("/", 1)[-1].upper()
            sn = str(payload.get("sn", ""))
            err = payload.get("errNo")
            _LOGGER.debug("V3 attr response dev=%s sn=%s errNo=%s", devid, sn, err)
            self._hass.loop.call_soon_threadsafe(
                self._resolve_attr_response, devid, sn, err
            )
            return

        if "/Resp/Op/" in msg.topic and isinstance(payload, dict):
            devid = msg.topic.rsplit("/", 1)[-1].upper()
            sn = str(payload.get("sn", ""))
            err = payload.get("errNo")
            _LOGGER.debug("V3 op response dev=%s sn=%s errNo=%s", devid, sn, err)
            self._hass.loop.call_soon_threadsafe(
                self._resolve_op_response, devid, sn, err
            )
            return

        if payload.get("event") == "invalidToken":
            _LOGGER.debug("DBG   -> invalidToken")
            self._hass.loop.call_soon_threadsafe(
                lambda: self._hass.async_create_background_task(self._reconnect("invalidToken"), "haier_cloud_reconnect")
            )
            return
        if payload.get("type") == "boundDevs" and payload.get("data"):
            try:
                inner = json.loads(base64.b64decode(payload["data"]))
            except Exception:  # noqa: BLE001
                _LOGGER.debug("DBG   -> boundDevs data not decodable, dropped")
                return
            _LOGGER.debug("Cloud device binding response received")
            for d in inner.get("devs") or []:
                _LOGGER.debug("DBG   -> device %s online=%s", d.get("id"), d.get("ol"))
                self._online[str(d.get("id", "")).upper()] = bool(d.get("ol"))
            self._hass.loop.call_soon_threadsafe(self._notify)
            return
        if payload.get("type") == "epp" and payload.get("data"):
            # topic: User/<token>/Ext/Push/<devId>
            devid = msg.topic.rsplit("/", 1)[-1].upper()
            try:
                frame = base64.b64decode(payload["data"])
            except Exception:  # noqa: BLE001
                _LOGGER.debug("DBG   -> epp data not base64, dropped")
                return
            ftype = frame[9] if len(frame) > 9 else None
            if len(frame) >= 12 and frame[9] in (0x02, 0x06):
                _LOGGER.debug(
                    "DBG   -> epp frame from %s accepted (type=0x%02x, known=%s): %s",
                    devid,
                    ftype,
                    devid in self._devices,
                    frame.hex(),
                )
                self._frames[devid] = frame
                self._online[devid] = True
                self._hass.loop.call_soon_threadsafe(self._notify)
            else:
                _LOGGER.debug(
                    "DBG   -> epp frame from %s DROPPED (len=%s type=%s): %s",
                    devid,
                    len(frame),
                    ftype,
                    frame.hex(),
                )
            return
        if "/Push/Dev/Attr/" in msg.topic:
            devid = msg.topic.rsplit("/", 1)[-1].upper()
            attrs = payload.get("attrs")

            if devid not in self._devices:
                return

            if not isinstance(attrs, list):
                return

            values = {}
            for item in attrs:
                if isinstance(item, dict):
                    for key, value in item.items():
                        if isinstance(value, (str, int, float, bool)):
                            values[key] = str(value)

            if values:
                self._attrs[devid] = {
                    **self._attrs.get(devid, {}),
                    **values,
                }
                _LOGGER.debug(
                    "DBG JSON attributes updated for %s: %s",
                    devid,
                    list(values),
                )
                self._hass.loop.call_soon_threadsafe(self._notify)
            return

        _LOGGER.debug("DBG   -> message type not handled, dropped")

    # ------------------------------------------------------------------ publish

    def _publish_epp(self, devid: str, frame: bytes) -> None:
        if not self._client or not self._token:
            _LOGGER.debug("DBG publish to %s skipped: client=%s token=%s",
                          devid, bool(self._client), bool(self._token))
            return
        self._sn += 1
        info = self._client.publish(
            f"User/{self._token}/Ext/Req/{devid.upper()}",
            json.dumps(
                {"sn": str(self._sn), "type": "epp", "data": base64.b64encode(frame).decode()}
            ),
        )
        _LOGGER.debug(
            "DBG MQTT OUT Req/%s sn=%s rc=%s connected=%s frame=%s",
            devid.upper(),
            self._sn,
            info.rc,
            self._client.is_connected(),
            frame.hex(),
        )



    def _resolve_attr_response(self, devid: str, sn: str, err: object) -> None:
        future = self._pending_attr_responses.get((devid, sn))
        if future is not None and not future.done():
            future.set_result(err)

    def _resolve_op_response(self, devid: str, sn: str, err: object) -> None:
        future = self._pending_op_responses.get((devid, sn))
        if future is not None and not future.done():
            future.set_result(err)

    def _v3_check_connection(self, devid: str) -> None:
        if devid not in self._devices:
            raise RuntimeError("Unknown cloud device")
        if not self._client or not self._client.is_connected() or not self._token:
            raise RuntimeError("Haier MQTT not connected")

    async def _async_v3_publish(
        self, devid: str, payload: dict, operation: bool, expected: dict[str, str]
    ) -> None:
        """Publish, correlate ACK by (device,SN), and verify fresh push status."""
        self._v3_check_connection(devid)
        self._sn += 1
        sn = str(self._sn)
        payload = {"sn": sn, **payload}
        pending = self._pending_op_responses if operation else self._pending_attr_responses
        response = self._hass.loop.create_future()
        changed = self._hass.loop.create_future()
        pending[(devid, sn)] = response

        def check_update() -> None:
            if not changed.done() and attrs_match(self.latest_attrs(devid), expected):
                changed.set_result(True)

        unsubscribe = self.add_listener(check_update)
        topic_part = "Req/Op" if operation else "Req/Attr/W"
        try:
            info = await self._hass.async_add_executor_job(
                self._client.publish,
                f"User/{self._token}/{topic_part}/{devid}",
                json.dumps(payload, separators=(",", ":")),
            )
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(f"V3 MQTT publish failed rc={info.rc}")
            try:
                err = await asyncio.wait_for(response, timeout=10)
            except asyncio.TimeoutError as exc:
                raise RuntimeError("No ACK received for V3 command") from exc
            if str(err) != "0":
                raise RuntimeError(f"Haier rejected V3 command errNo={err}")
            try:
                await asyncio.wait_for(changed, timeout=20)
            except asyncio.TimeoutError as exc:
                raise RuntimeError(
                    "V3 command ACKed but no matching device attribute push received; "
                    "check the device before retrying"
                ) from exc
            _LOGGER.debug("V3 confirmed dev=%s sn=%s attrs=%s", devid, sn, list(expected))
        finally:
            unsubscribe()
            pending.pop((devid, sn), None)

    async def async_write_v3_power(self, devid: str, power: bool) -> None:
        """Send single V3 attribute (power) without requiring full state."""
        devid = devid.upper()
        if not isinstance(power, bool):
            raise ValueError("Expected boolean power")
        value = "true" if power else "false"
        lock = self._control_locks.setdefault(devid, asyncio.Lock())
        async with lock:
            self._v3_check_connection(devid)
            if same_attr("onOffStatus", self.latest_attrs(devid).get("onOffStatus"), value):
                return
            await self._async_v3_publish(
                devid, {"attr": "onOffStatus", "value": value},
                operation=False, expected={"onOffStatus": value}
            )

    async def async_write_v3_attrs(self, devid: str, changes: dict[str, str]) -> None:
        """Issue complete grSetDAC with remaining values preserved from device."""
        devid = devid.upper()
        lock = self._control_locks.setdefault(devid, asyncio.Lock())
        async with lock:
            self._v3_check_connection(devid)
            attrs = self.latest_attrs(devid)
            if normalized(attrs.get("onOffStatus", "")).lower() not in ("true", "1"):
                raise RuntimeError("V3 power not confirmed ON; refusing grSetDAC")
            if any(k not in attrs for k in changes):
                raise RuntimeError("V3 requested attribute not reported by this device")
            if attrs_match(attrs, changes):
                return
            # Require a complete snapshot, never fill unknown operational values.
            arguments = make_grsetdac_args(attrs, changes)
            await self._async_v3_publish(
                devid, {"op": "grSetDAC", "args": arguments},
                operation=True, expected=changes,
            )

    async def async_poll(self, devid: str) -> None:
        from .codec import POLL_FRAME

        await self._hass.async_add_executor_job(self._publish_epp, devid, POLL_FRAME)

    async def async_send_frame(self, devid: str, frame: bytes) -> None:
        await self._hass.async_add_executor_job(self._publish_epp, devid, frame)

    async def async_stop(self) -> None:
        self._stopped = True
        if self._refresh_unsub:
            self._refresh_unsub.cancel()
        if self._client:
            await self._hass.async_add_executor_job(self._client.loop_stop)
            try:
                self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass


class CloudAuthError(Exception):
    """Login/token failure."""
