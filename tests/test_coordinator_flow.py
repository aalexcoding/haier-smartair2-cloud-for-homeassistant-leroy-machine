"""Coordinator flow tests with small HA stubs (no real cloud or HA instance)."""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import types

import pytest

BASE = Path(__file__).resolve().parents[1] / 'custom_components' / 'haier_smartair2'


def load_coordinator(monkeypatch):
    prefix = 'isolated_haier'
    fakepkg = types.ModuleType(prefix)
    fakepkg.__path__ = [str(BASE)]
    monkeypatch.setitem(sys.modules, prefix, fakepkg)

    h_core = types.ModuleType('homeassistant.core')
    h_core.HomeAssistant = type('HomeAssistant', (), {})
    monkeypatch.setitem(sys.modules, 'homeassistant', types.ModuleType('homeassistant'))
    monkeypatch.setitem(sys.modules, 'homeassistant.core', h_core)
    h_helpers = types.ModuleType('homeassistant.helpers')
    h_helpers.__path__ = []
    monkeypatch.setitem(sys.modules, 'homeassistant.helpers', h_helpers)
    h_coord = types.ModuleType('homeassistant.helpers.update_coordinator')

    class FakeDataUpdateCoordinator:
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, *args, **kwargs):
            self.data = None

        def async_set_updated_data(self, state):
            self.data = state

        async def async_request_refresh(self):
            pass

    h_coord.DataUpdateCoordinator = FakeDataUpdateCoordinator
    monkeypatch.setitem(sys.modules, 'homeassistant.helpers.update_coordinator', h_coord)

    const = types.ModuleType(f'{prefix}.const')
    for name, value in dict(
        SCAN_INTERVAL_SECONDS=30, MODE_AUTO=0, MODE_COOL=1,
        MODE_HEAT=2, MODE_FAN=3, MODE_DRY=4,
        FAN_HIGH=0, FAN_MID=1, FAN_LOW=2, FAN_AUTO=3,
    ).items():
        setattr(const, name, value)
    monkeypatch.setitem(sys.modules, f'{prefix}.const', const)

    codec = types.ModuleType(f'{prefix}.codec')

    class FakeCodec:
        def __init__(self):
            self.supports_fan = True

        def encode_set(self, state, **changes):
            return b'original_EPP_write'

        def decode(self, frame):
            return FakeHaierState(raw_block=frame)

    class FakeV3(FakeCodec):
        pass

    class FakeHaierState:
        def __init__(self, **kwargs):
            self.raw_block = kwargs.get('raw_block', b'')
            self.power = kwargs.get('power', None)
            self.mode = kwargs.get('mode', None)
            self.fan = kwargs.get('fan', None)
            self.current_temp = kwargs.get('current_temp', None)
            self.target_temp = kwargs.get('target_temp', None)

        def merged(self, **changes):
            return FakeHaierState(**{**self.__dict__, **changes})

    codec.Codec = FakeCodec
    codec.CodecV3 = FakeV3
    codec.HaierState = FakeHaierState
    monkeypatch.setitem(sys.modules, f'{prefix}.codec', codec)

    spec = importlib.util.spec_from_file_location(f'{prefix}.v3_cloud', BASE/'v3_cloud.py')
    v3 = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, f'{prefix}.v3_cloud', v3)
    spec.loader.exec_module(v3)

    spec = importlib.util.spec_from_file_location(f'{prefix}.coordinator', BASE/'coordinator.py')
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, f'{prefix}.coordinator', mod)
    spec.loader.exec_module(mod)
    return mod, FakeV3, FakeCodec


class FakeTransport:
    def __init__(self, power='false', mode='4', fan='5'):
        self.attrs = {'onOffStatus': power, 'operationMode': mode, 'windSpeed': fan}
        self.commands = []
        self.listeners = []
        self.frames = {}

    def add_listener(self, cb):
        self.listeners.append(cb)

    def latest_attrs(self, devid):
        return dict(self.attrs)

    def latest_frame(self, devid):
        return self.frames.get(devid)

    async def async_write_v3_power(self, devid, value):
        self.commands.append((devid, 'power', value))
        self.attrs['onOffStatus'] = str(value).lower()

    async def async_write_v3_attrs(self, devid, value):
        self.commands.append((devid, 'attrs', value.copy()))
        self.attrs.update(value)

    async def async_send_frame(self, devid, frame):
        self.commands.append((devid, 'frame', frame))


@pytest.mark.asyncio
async def test_power_from_off_then_fan_only_sequence(monkeypatch):
    mod, FakeV3, _ = load_coordinator(monkeypatch)
    dev = 'A' * 16
    transport = FakeTransport(power='false', mode='4', fan='5')
    coord = mod.HaierCoordinator(None, transport, FakeV3(), dev, 'Demo', True)
    await coord.async_apply(power=True, mode=3)
    assert transport.commands == [
        (dev, 'power', True),
        (dev, 'attrs', {'windSpeed': '3'}),
        (dev, 'attrs', {'operationMode': '6'}),
    ]


@pytest.mark.asyncio
async def test_each_device_is_addressed_independently(monkeypatch):
    mod, FakeV3, _ = load_coordinator(monkeypatch)
    t1 = FakeTransport(power='true', mode='4', fan='5')
    t2 = FakeTransport(power='true', mode='1', fan='2')
    # Real HA shares one HaierCloudClient for these two devices; here the
    # coordinators still need to send their own explicit IDs.
    c1 = mod.HaierCoordinator(None, t1, FakeV3(), 'A'*16, 'Room 1', True)
    c2 = mod.HaierCoordinator(None, t2, FakeV3(), 'B'*16, 'Room 2', True)
    await c1.async_apply(power=True, mode=1)
    await c2.async_apply(power=True, target_temp=25)
    assert t1.commands == [('A'*16, 'attrs', {'operationMode':'1'})]
    assert t2.commands == [('B'*16, 'attrs', {'targetTemperature':'25'})]


@pytest.mark.asyncio
async def test_original_local_epp_write_path_is_preserved(monkeypatch):
    mod, _, FakeCodec = load_coordinator(monkeypatch)
    t = FakeTransport()
    coord = mod.HaierCoordinator(None, t, FakeCodec(), 'C'*16, 'Local', False)
    await coord.async_apply(power=False)
    assert t.commands == [('C'*16, 'frame', b'original_EPP_write')]


@pytest.mark.asyncio
async def test_cloud_v2_refuses_missing_epp_read(monkeypatch):
    mod, _, FakeCodec = load_coordinator(monkeypatch)
    t = FakeTransport()
    coord = mod.HaierCoordinator(None, t, FakeCodec(), 'D'*16, 'Cloud V2', True)
    with pytest.raises(RuntimeError, match='no valid EPP status'):
        await coord.async_apply(power=True)
    assert t.commands == []

@pytest.mark.asyncio
async def test_v3_online_without_attrs_reports_unknown_and_skips_epp(monkeypatch):
    mod, FakeV3, _ = load_coordinator(monkeypatch)

    class UninitializedCloud(FakeTransport):
        def __init__(self):
            super().__init__()
            self.attrs = {}

        async def async_poll(self, devid):
            raise AssertionError('V3 cloud must not send legacy EPP polls')

    transport = UninitializedCloud()
    coord = mod.HaierCoordinator(None, transport, FakeV3(), 'A' * 16, 'Unknown', True)
    coord._on_push()
    assert coord.data is not None
    assert coord.data.power is None
    state = await coord._async_update_data()
    assert state.power is None


@pytest.mark.asyncio
async def test_v3_power_command_is_allowed_without_initial_snapshot(monkeypatch):
    mod, FakeV3, _ = load_coordinator(monkeypatch)
    transport = FakeTransport()
    transport.attrs = {}
    coord = mod.HaierCoordinator(None, transport, FakeV3(), 'A' * 16, 'Unknown', True)
    await coord.async_apply(power=False)
    assert transport.commands == [('A' * 16, 'power', False)]
