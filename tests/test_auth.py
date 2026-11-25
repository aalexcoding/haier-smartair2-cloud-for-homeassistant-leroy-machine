"""Authentication lifecycle regression tests with lightweight Home Assistant stubs."""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import time
import types
from unittest.mock import AsyncMock, Mock

import pytest

BASE = Path(__file__).resolve().parents[1] / "custom_components" / "haier_smartair2"
PREFIX = "auth_haier"


@pytest.fixture
def modules(monkeypatch):
    """Load the real integration without starting HA or contacting Haier."""
    def stub(name, **attrs):
        module = types.ModuleType(name)
        module.__path__ = []
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, module)
        return module

    class ConfigEntry:
        def __class_getitem__(cls, item):
            return cls

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__()

        def async_show_form(self, **kwargs):
            return {"type": "form", **kwargs}

    class ConfigEntryAuthFailed(Exception):
        pass

    class ConfigEntryNotReady(Exception):
        pass

    stub("homeassistant")
    stub("homeassistant.core", HomeAssistant=object, callback=lambda fn: fn)
    stub("homeassistant.const", Platform=types.SimpleNamespace(CLIMATE="climate", SENSOR="sensor", SWITCH="switch"))
    stub("homeassistant.config_entries", ConfigEntry=ConfigEntry, ConfigFlow=ConfigFlow,
         ConfigFlowResult=dict, OptionsFlow=ConfigFlow)
    stub("homeassistant.exceptions", ConfigEntryAuthFailed=ConfigEntryAuthFailed,
         ConfigEntryNotReady=ConfigEntryNotReady)
    stub("homeassistant.helpers")
    stub("homeassistant.helpers.aiohttp_client", async_get_clientsession=Mock())
    stub("homeassistant.helpers.selector", SelectSelector=Mock(), SelectSelectorConfig=Mock(), SelectSelectorMode=Mock())
    stub("homeassistant.util")
    stub("homeassistant.util.ssl", get_default_context=Mock())
    package = stub(PREFIX)
    package.__path__ = [str(BASE)]
    stub(f"{PREFIX}.coordinator", HaierCoordinator=Mock())
    stub(f"{PREFIX}.codec", codec_for_type=Mock())

    def load(name, filename):
        spec = importlib.util.spec_from_file_location(name, BASE / filename)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        return module

    # Register imported children with monkeypatch so other tests remain isolated.
    for name in ("const", "v3_cloud", "local"):
        load(f"{PREFIX}.{name}", f"{name}.py")
    cloud = load(f"{PREFIX}.cloud", "cloud.py")
    flow = load(f"{PREFIX}.config_flow", "config_flow.py")
    integration = load(PREFIX, "__init__.py")
    return types.SimpleNamespace(cloud=cloud, flow=flow, integration=integration)


class Timer:
    def __init__(self, delay, callback):
        self.delay = delay
        self.callback = callback
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class FakeLoop:
    def __init__(self):
        self.timers = []

    def call_later(self, delay, callback, *args):
        timer = Timer(delay, (lambda: callback(*args)) if args else callback)
        self.timers.append(timer)
        return timer

    def call_soon_threadsafe(self, callback, *args):
        callback(*args)


@pytest.fixture
def hass():
    tasks = []

    def create_task(coro, name):
        task = asyncio.create_task(coro, name=name)
        tasks.append(task)
        return task

    async def executor(fn, *args):
        return fn(*args)

    return types.SimpleNamespace(
        loop=FakeLoop(), tasks=tasks,
        async_create_background_task=create_task,
        async_add_executor_job=executor,
        config_entries=types.SimpleNamespace(async_reload=AsyncMock(), async_update_entry=Mock()),
    )


@pytest.fixture
def client(modules, hass, monkeypatch):
    monkeypatch.setattr(modules.cloud.asyncio, "sleep", AsyncMock())
    return modules.cloud.HaierCloudClient(hass, "user@example.com", "old", "gateway")


async def fire_retry(hass):
    """Run the most recently scheduled retry callback to completion."""
    hass.loop.timers[-1].callback()
    await hass.tasks[-1]


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["disconnect", "token refresh", "invalidToken", "retry"])
async def test_auth_failure_starts_reauth_once_and_never_retries(modules, client, hass, monkeypatch, reason):
    entry = types.SimpleNamespace(async_start_reauth=Mock())
    client._on_auth_failed = lambda: entry.async_start_reauth(hass)
    login = AsyncMock(side_effect=modules.cloud.CloudAuthError("wrong password"))
    monkeypatch.setattr(client, "async_login", login)
    client._online["DEVICE"] = True
    client._schedule_refresh()
    refresh = hass.loop.timers[-1]
    notify = Mock()
    client.add_listener(notify)

    await client._reconnect(reason)
    assert refresh.cancelled
    # One rejection may be a rate limit or maintenance: retry with back-off.
    assert [t.delay for t in hass.loop.timers[1:]] == [30]
    entry.async_start_reauth.assert_not_called()
    await fire_retry(hass)
    entry.async_start_reauth.assert_not_called()
    await fire_retry(hass)

    assert login.await_count == modules.cloud._AUTH_REJECTIONS_BEFORE_REAUTH
    assert client._refresh_unsub is None
    assert client._retry_unsub is None
    assert not client.is_online("DEVICE")
    notify.assert_called_once()
    entry.async_start_reauth.assert_called_once_with(hass)

    # Even stale queued callbacks and direct reconnect calls cannot log in again.
    timers = len(hass.loop.timers)
    refresh.callback()
    client._on_disconnect(None, None, None, 1)
    client._on_message(None, None, types.SimpleNamespace(topic="topic", payload=b'{"event":"invalidToken"}'))
    await asyncio.gather(*hass.tasks)
    await client._reconnect("disconnect")
    client._schedule_refresh()
    client._schedule_watchdog()
    assert len(hass.loop.timers) == timers
    assert login.await_count == modules.cloud._AUTH_REJECTIONS_BEFORE_REAUTH
    entry.async_start_reauth.assert_called_once()


@pytest.mark.asyncio
async def test_successful_login_resets_transient_rejections(modules, client, hass, monkeypatch):
    client._on_auth_failed = Mock()
    connect = AsyncMock(side_effect=[modules.cloud.CloudAuthError(), modules.cloud.CloudAuthError(), None])
    monkeypatch.setattr(client, "_connect", connect)
    await client._reconnect("disconnect")
    await fire_retry(hass)
    client._auth_rejections = 0  # what a successful async_login does
    await fire_retry(hass)
    assert not client._auth_failed
    client._on_auth_failed.assert_not_called()


@pytest.mark.asyncio
async def test_network_backoff_caps_and_resets_only_when_session_works(modules, client, hass, monkeypatch):
    connect = AsyncMock(side_effect=OSError("network down"))
    monkeypatch.setattr(client, "_connect", connect)
    client._schedule_refresh()
    refresh = hass.loop.timers[-1]
    await client._reconnect("disconnect")
    assert refresh.cancelled

    for count, delay in enumerate([30, 60, 120, 240, 300, 300], start=1):
        timer = hass.loop.timers[-1]
        assert timer.delay == delay
        await client._reconnect("invalidToken")  # cannot bypass a pending retry
        assert connect.await_count == count
        timer.callback()
        if count == 6:
            connect.side_effect = None
        await hass.tasks[-1]

    assert client._retry_unsub is None
    assert hass.loop.timers[-1].delay == modules.cloud.TOKEN_REFRESH_SECONDS
    # Opening a socket is not enough: a broker that refuses us keeps backing off.
    assert client._retry_delay == 300

    session = types.SimpleNamespace(is_connected=lambda: True)
    client._client = session
    client._set_session_ready(session)
    assert client._retry_delay == 30


@pytest.mark.asyncio
async def test_auth_failure_after_network_retry_cancels_all_future_work(modules, client, hass, monkeypatch):
    client._on_auth_failed = Mock()
    auth = modules.cloud.CloudAuthError
    connect = AsyncMock(side_effect=[OSError(), auth(), auth(), auth()])
    monkeypatch.setattr(client, "_connect", connect)
    await client._reconnect("disconnect")
    for _ in range(3):
        await fire_retry(hass)
    assert client._auth_failed
    assert client._retry_unsub is None
    assert client._refresh_unsub is None
    await client._reconnect("token refresh")
    assert connect.await_count == 4
    client._on_auth_failed.assert_called_once()


@pytest.mark.asyncio
async def test_stop_cancels_retry_and_stale_callback_cannot_connect(client, hass, monkeypatch):
    connect = AsyncMock(side_effect=OSError())
    monkeypatch.setattr(client, "_connect", connect)
    await client._reconnect("disconnect")
    retry = hass.loop.timers[-1]
    await client.async_stop()
    assert retry.cancelled
    retry.callback()
    await hass.tasks[-1]
    connect.assert_awaited_once()
    assert client._refresh_unsub is None
    assert client._retry_unsub is None


@pytest.mark.asyncio
async def test_stop_cancels_in_flight_reconnect(client, hass, monkeypatch):
    started = asyncio.Event()

    async def connecting():
        started.set()
        await asyncio.Event().wait()

    connect = AsyncMock(side_effect=connecting)
    monkeypatch.setattr(client, "_connect", connect)
    task = asyncio.create_task(client._reconnect("disconnect"))
    await started.wait()
    await client.async_stop()
    assert task.cancelled()
    assert client._reconnect_task is None
    assert not client._reconnecting
    assert not hass.loop.timers


@pytest.fixture
def entry():
    return types.SimpleNamespace(
        entry_id="existing-entry", unique_id="user@example.com",
        data={"username": "user@example.com", "password": "old", "region": "eu",
              "local_ips": "AABBCCDDEEFF:192.0.2.1", "client_id": "stable-client"},
        options={"region": "us"}, async_start_reauth=Mock(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["auth", "network", None])
async def test_reauth_validates_and_updates_only_password(modules, hass, entry, monkeypatch, failure):
    flow = modules.flow.HaierConfigFlow()
    flow.hass = hass
    flow._get_reauth_entry = Mock(return_value=entry)
    flow.async_update_reload_and_abort = Mock(return_value={"type": "abort", "reason": "reauth_successful"})
    cloud = Mock()
    cloud.async_login = AsyncMock()
    if failure:
        cloud.async_login.side_effect = modules.cloud.CloudAuthError() if failure == "auth" else OSError()
    factory = Mock(return_value=cloud)
    monkeypatch.setattr(modules.flow, "HaierCloudClient", factory)

    form = await flow.async_step_reauth(entry.data)
    assert form["step_id"] == "reauth_confirm"
    assert form["data_schema"]({"password": "new"}) == {"password": "new"}
    assert form["description_placeholders"] == {"username": "user@example.com"}
    factory.assert_not_called()
    result = await flow.async_step_reauth_confirm({"password": "new"})
    factory.assert_called_once_with(hass, "user@example.com", "new", "gw-gea-us.haieriot.net", "stable-client")
    cloud.async_login.assert_awaited_once()
    if failure:
        assert result["errors"] == {"base": "invalid_auth" if failure == "auth" else "cannot_connect"}
        flow.async_update_reload_and_abort.assert_not_called()
    else:
        assert result == {"type": "abort", "reason": "reauth_successful"}
        flow.async_update_reload_and_abort.assert_called_once_with(entry, data_updates={"password": "new"})
    assert entry.data["password"] == "old"  # Only the HA update helper may modify it.


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["devices", "start"])
@pytest.mark.parametrize("failure", ["auth", "network"])
async def test_setup_auth_failure_is_not_retried(modules, hass, entry, monkeypatch, phase, failure):
    integration = modules.integration
    entry.options = {}  # Keep this device on the cloud transport.
    entry.data = {**entry.data, "local_ips": ""}
    cloud = Mock()
    cloud.async_get_devices = AsyncMock(return_value=[{"id": "DEVICE", "name": "Room"}])
    cloud.async_start = AsyncMock()
    cloud.async_stop = AsyncMock()
    error = modules.cloud.CloudAuthError() if failure == "auth" else OSError()
    method = cloud.async_get_devices if phase == "devices" else cloud.async_start
    method.side_effect = error
    factory = Mock(return_value=cloud)
    monkeypatch.setattr(integration, "HaierCloudClient", factory)
    expected = integration.ConfigEntryAuthFailed if failure == "auth" else integration.ConfigEntryNotReady
    with pytest.raises(expected):
        await integration.async_setup_entry(hass, entry)
    assert cloud.async_stop.await_count == (1 if phase == "start" else 0)
    factory.call_args.kwargs["on_auth_failed"]()
    entry.async_start_reauth.assert_called_once_with(hass)


@pytest.mark.asyncio
async def test_options_changes_reload_without_update_listener(modules, hass, entry):
    flow = modules.flow.HaierOptionsFlow()
    flow.hass = hass
    flow.config_entry = entry
    flow.async_create_entry = Mock(return_value={"type": "create_entry"})
    options = {"region": "sg", "local_ips": ""}
    await flow.async_step_init(options)
    hass.config_entries.async_update_entry.assert_called_once_with(entry, options=options)
    hass.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)
    flow.async_create_entry.assert_called_once_with(title="", data=options)


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["auth_failed", "stopped"])
async def test_blocked_client_cannot_send_stored_password(modules, client, monkeypatch, state):
    session = Mock()
    monkeypatch.setattr(modules.cloud, "async_get_clientsession", session)
    setattr(client, f"_{state}", True)
    with pytest.raises(modules.cloud.CloudAuthError):
        await client.async_login()
    await client._connect()
    session.assert_not_called()


@pytest.mark.asyncio
async def test_setup_auth_failure_cleans_up_already_started_local_clients(modules, hass, entry, monkeypatch):
    integration = modules.integration
    local = types.SimpleNamespace(async_start=AsyncMock(), async_poll=AsyncMock(), async_stop=AsyncMock())
    monkeypatch.setattr(integration, "HaierLocalClient", Mock(return_value=local))
    cloud = Mock()
    cloud.async_get_devices = AsyncMock(return_value=[{"id": "AABBCCDDEEFF"}, {"id": "CLOUD"}])
    cloud.async_start = AsyncMock(side_effect=modules.cloud.CloudAuthError())
    cloud.async_stop = AsyncMock()
    monkeypatch.setattr(integration, "HaierCloudClient", Mock(return_value=cloud))
    with pytest.raises(integration.ConfigEntryAuthFailed):
        await integration.async_setup_entry(hass, entry)
    local.async_start.assert_awaited_once()
    local.async_stop.assert_awaited_once()
    cloud.async_stop.assert_awaited_once()


class FakeMqtt:
    def __init__(self, connected=False):
        self.connected = connected
        self.loop_stop = Mock()
        self.disconnect = Mock()

    def is_connected(self):
        return self.connected


def ready_session(client, connected=True):
    session = FakeMqtt(connected)
    client._client = session
    client._token = "token"
    client._set_session_ready(session)
    return session


@pytest.mark.asyncio
async def test_watchdog_reconnects_after_lost_disconnect_callback(modules, client, hass, monkeypatch):
    # Session died but on_disconnect never reached us: nothing is repairing it.
    client._client = FakeMqtt(connected=False)
    client._token = "token"
    client._connect_started = time.monotonic() - 60
    reconnect = AsyncMock()
    monkeypatch.setattr(client, "_reconnect", reconnect)
    client._schedule_watchdog()
    hass.loop.timers[-1].callback()
    await asyncio.gather(*hass.tasks)
    reconnect.assert_awaited_once_with("watchdog")
    assert client._watchdog_unsub is hass.loop.timers[-1]

    # Something already repairing it, or a session still inside its grace window.
    client._reconnecting = True
    hass.loop.timers[-1].callback()
    client._reconnecting = False
    client._retry_unsub = Timer(30, Mock())
    hass.loop.timers[-1].callback()
    client._retry_unsub = None
    client._connect_started = time.monotonic()
    hass.loop.timers[-1].callback()
    # A healthy session, an auth failure or a stop must not trigger reconnects.
    ready_session(client)
    hass.loop.timers[-1].callback()
    client._auth_failed = True
    hass.loop.timers[-1].callback()
    await asyncio.gather(*hass.tasks)
    reconnect.assert_awaited_once()
    assert client._watchdog_unsub is None


@pytest.mark.asyncio
async def test_watchdog_cancels_a_stuck_reconnect(modules, client, hass, monkeypatch):
    started = asyncio.Event()

    async def hang():
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(client, "_connect", hang)
    task = asyncio.create_task(client._reconnect("disconnect"))
    await started.wait()  # asyncio.sleep is mocked by the fixture
    assert client._reconnecting
    client._reconnect_started -= modules.cloud._STUCK_RECONNECT_SECONDS + 1
    client._schedule_watchdog()
    hass.loop.timers[-1].callback()
    await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()
    assert not client._reconnecting
    assert client._watchdog_unsub is not None  # keeps watching; next tick reconnects


@pytest.mark.asyncio
async def test_connect_timeout_discards_half_open_client(modules, client, hass, monkeypatch):
    half_open = FakeMqtt()

    async def hang():
        client._client = half_open
        await asyncio.Event().wait()

    monkeypatch.setattr(client, "_connect_unlocked", hang)
    monkeypatch.setattr(modules.cloud, "_CONNECT_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(TimeoutError):
        await client._connect()
    assert client._client is None
    half_open.loop_stop.assert_called_once()
    half_open.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_command_cancelling_retry_always_starts_reconnect(modules, client, hass, monkeypatch):
    # The last attempt failed inside connect(): a dead client inside its grace
    # window and a pending back-off retry. The command must not just wait.
    client._devices.add("DEVICE")
    client._client = FakeMqtt(connected=False)
    client._connect_started = time.monotonic()
    client._retry_delay = 120
    pending_retry = client._retry_unsub = Timer(60, Mock())

    async def reconnect(reason):
        ready_session(client)

    monkeypatch.setattr(client, "_reconnect", AsyncMock(side_effect=reconnect))

    async def let_reconnect_run(_):
        await asyncio.gather(*hass.tasks)

    monkeypatch.setattr(modules.cloud.asyncio, "sleep", AsyncMock(side_effect=let_reconnect_run))
    await client._async_ensure_connected("DEVICE")
    assert pending_retry.cancelled
    client._reconnect.assert_awaited_once_with("command while disconnected")
    assert client._retry_delay == 30  # reset by the working session, not by the command


@pytest.mark.asyncio
async def test_commands_cannot_hammer_login(modules, client, hass, monkeypatch):
    client._devices.add("DEVICE")
    client._retry_unsub = Timer(60, Mock())
    client._last_attempt = time.monotonic()
    monkeypatch.setattr(client, "_reconnect", AsyncMock())
    monkeypatch.setattr(modules.cloud, "_COMMAND_CONNECT_WAIT_SECONDS", 0)
    with pytest.raises(RuntimeError, match="not connected"):
        await client._async_ensure_connected("DEVICE")
    client._reconnect.assert_not_called()
    assert not client._retry_unsub.cancelled


@pytest.mark.asyncio
@pytest.mark.parametrize("state, message", [("auth_failed", "reauthenticate"), ("stopped", "stopped")])
async def test_command_on_unusable_client_fails_at_once(client, state, message):
    client._devices.add("DEVICE")
    setattr(client, f"_{state}", True)
    with pytest.raises(RuntimeError, match=message):
        await client._async_ensure_connected("DEVICE")


def test_session_ready_only_after_our_suback(modules, client, hass):
    session = FakeMqtt(connected=True)
    client._client = session
    client._token = "token"
    client._sub_mid = 7
    assert not client._is_connected()  # CONNACK alone is not enough
    client._on_subscribe(session, None, 8, [], None)
    assert not client._is_connected()
    client._on_subscribe(session, None, 7, [types.SimpleNamespace(is_failure=True)], None)
    assert not client._is_connected()
    client._on_subscribe(session, None, 7, [types.SimpleNamespace(is_failure=False)], None)
    assert client._is_connected()


def test_missing_suback_falls_back_to_ready(client, hass):
    session = FakeMqtt(connected=True)
    client._client = session
    client._token = "token"
    client._arm_suback_fallback(session)
    hass.loop.timers[-1].callback()
    assert client._is_connected()


@pytest.mark.asyncio
async def test_disconnect_handling(client, hass, monkeypatch):
    reconnect = AsyncMock()
    monkeypatch.setattr(client, "_reconnect", reconnect)
    # A stale client we already replaced is ignored.
    ready_session(client)
    client._handle_disconnect(FakeMqtt())
    assert client._is_connected()
    # A working session that drops reconnects at once.
    client._handle_disconnect(client._client)
    await asyncio.gather(*hass.tasks)
    reconnect.assert_awaited_once_with("disconnect")
    # A session refused or dropped before it ever worked backs off instead.
    client._handle_disconnect(client._client)
    reconnect.assert_awaited_once()
    assert client._retry_unsub is not None and client._retry_unsub.delay == 30


def test_availability_survives_short_outages_only(client, hass):
    client._online["DEVICE"] = True
    listener = Mock()
    client.add_listener(listener)
    ready_session(client)
    client._mark_disconnected()
    assert client.is_online("DEVICE")  # e.g. the token-refresh reconnect
    client._disconnected_since -= 61
    assert not client.is_online("DEVICE")
    listener.reset_mock()
    hass.loop.timers[-1].callback()  # grace expiry pushes the new availability
    listener.assert_called_once()
    ready_session(client)
    assert client.is_online("DEVICE")


@pytest.mark.parametrize("payload", [
    b'{"type":"boundDevs","data":"WzEsMl0="}',              # base64 of [1,2]
    b'{"type":"boundDevs","data":"eyJkZXZzIjpbMSwieCJdfQ=="}',  # {"devs":[1,"x"]}
    b'{"type":"boundDevs","data":"eyJkZXZzIjoiYWJjIn0="}',  # {"devs":"abc"}
])
def test_malformed_messages_cannot_kill_the_network_thread(client, payload):
    client._on_message(None, None, types.SimpleNamespace(topic="Client/x/Business/Down", payload=payload))

    class BadTopic:
        payload = b"{}"

        @property
        def topic(self):
            raise UnicodeDecodeError("utf-8", b"", 0, 1, "bad")

    client._on_message(None, None, BadTopic())


def test_gateway_discovery_eof_does_not_spin(modules):
    sock = types.SimpleNamespace(recv=Mock(return_value=b""))
    with pytest.raises(ConnectionError):
        modules.cloud._recv_or_raise(sock)
