"""Authentication lifecycle regression tests with lightweight Home Assistant stubs."""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
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

    def call_later(self, delay, callback):
        timer = Timer(delay, callback)
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
    assert client._refresh_unsub is None
    assert client._retry_unsub is None
    assert not client.is_online("DEVICE")
    notify.assert_called_once()
    entry.async_start_reauth.assert_called_once_with(hass)

    # Even stale queued callbacks and direct reconnect calls cannot log in again.
    refresh.callback()
    client._on_disconnect(None, None, None, 1)
    client._on_message(None, None, types.SimpleNamespace(topic="topic", payload=b'{"event":"invalidToken"}'))
    await asyncio.gather(*hass.tasks)
    await client._reconnect("disconnect")
    client._schedule_refresh()
    assert len(hass.loop.timers) == 1
    login.assert_awaited_once()
    entry.async_start_reauth.assert_called_once()


@pytest.mark.asyncio
async def test_network_backoff_caps_resets_and_cannot_be_bypassed(modules, client, hass, monkeypatch):
    connect = AsyncMock(side_effect=OSError("network down"))
    monkeypatch.setattr(client, "_connect", connect)
    client._schedule_refresh()
    refresh = hass.loop.timers[-1]
    await client._reconnect("disconnect")
    assert refresh.cancelled

    for count, delay in enumerate([30, 60, 120, 240, 300, 300], start=1):
        timer = hass.loop.timers[-1]
        assert timer.delay == delay
        await client._reconnect("invalidToken")
        assert connect.await_count == count
        timer.callback()
        if count == 6:
            connect.side_effect = None
        await hass.tasks[-1]

    assert client._retry_unsub is None
    assert hass.loop.timers[-1].delay == modules.cloud.TOKEN_REFRESH_SECONDS
    connect.side_effect = OSError("network down again")
    await client._reconnect("disconnect")
    assert hass.loop.timers[-1].delay == 30


@pytest.mark.asyncio
async def test_auth_failure_after_network_retry_cancels_all_future_work(modules, client, hass, monkeypatch):
    client._on_auth_failed = Mock()
    connect = AsyncMock(side_effect=[OSError(), modules.cloud.CloudAuthError()])
    monkeypatch.setattr(client, "_connect", connect)
    await client._reconnect("disconnect")
    hass.loop.timers[-1].callback()
    await hass.tasks[-1]
    assert client._auth_failed
    assert client._retry_unsub is None
    assert client._refresh_unsub is None
    await client._reconnect("token refresh")
    assert connect.await_count == 2
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
