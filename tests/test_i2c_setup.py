"""Config-entry setup and config flow for I2C open/close and address errors.

Home Assistant is stubbed so these tests run with pytest alone. SMBus() must
run inside hass.async_add_executor_job; calling it on the event loop fails.
"""

from __future__ import annotations

import asyncio
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "waveshare_ups_hat"


class FakeBus:
    def __init__(self, bus_no: int, factory: BusFactory) -> None:
        self.bus_no = bus_no
        self.factory = factory
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1

    def read_i2c_block_data(self, addr: int, register: int, length: int) -> list[int]:
        if self.factory.read_error is not None:
            raise self.factory.read_error
        return [0] * length


class BusFactory:
    def __init__(self) -> None:
        self.buses: list[FakeBus] = []
        self.init_error: BaseException | None = None
        self.read_error: BaseException | None = None
        self.in_executor = False

    def reset(self) -> None:
        self.buses.clear()
        self.init_error = None
        self.read_error = None
        self.in_executor = False

    def __call__(self, bus_no: int) -> FakeBus:
        if not self.in_executor:
            raise AssertionError("SMBus() opened /dev/i2c on the event loop")
        if self.init_error is not None:
            raise self.init_error
        bus = FakeBus(bus_no, self)
        self.buses.append(bus)
        return bus


class _ConfigEntries:
    def __init__(self) -> None:
        self.forwarded: list = []
        self.unload_result = True

    async def async_forward_entry_setups(self, entry, platforms) -> None:
        self.forwarded.append((entry.entry_id, list(platforms)))

    async def async_unload_platforms(self, entry, platforms) -> bool:
        return self.unload_result


class _Hass:
    def __init__(self, factory: BusFactory) -> None:
        self.factory = factory
        self.data: dict = {}
        self.config_entries = _ConfigEntries()
        self.jobs: list[str] = []

    async def async_add_executor_job(self, func, *args):
        self.jobs.append(getattr(func, "__name__", type(func).__name__))
        self.factory.in_executor = True
        try:
            return func(*args)
        finally:
            self.factory.in_executor = False


class _Entry:
    def __init__(self, bus: int = 1, addr: int = 0x2D) -> None:
        self.entry_id = "entry-1"
        self.data = {"bus": bus, "addr": addr}


def _ensure_module(name: str) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    return module


def _install_stubs(factory: BusFactory) -> None:
    ha = _ensure_module("homeassistant")
    ha.__path__ = []

    exceptions = _ensure_module("homeassistant.exceptions")

    class ConfigEntryNotReady(Exception):
        pass

    exceptions.ConfigEntryNotReady = ConfigEntryNotReady

    config_entries = _ensure_module("homeassistant.config_entries")

    class ConfigEntry:
        pass

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__()

        def __init__(self) -> None:
            self.hass = None
            self.unique_id = None

        async def async_set_unique_id(self, unique_id, raise_on_progress=True):
            self.unique_id = unique_id

        def _abort_if_unique_id_configured(self):
            return None

        def async_show_form(self, *, step_id, data_schema=None, errors=None, **kwargs):
            return {
                "type": "form",
                "step_id": step_id,
                "errors": errors or {},
                "data_schema": data_schema,
            }

        def async_create_entry(self, *, title, data, **kwargs):
            return {"type": "create_entry", "title": title, "data": data}

    config_entries.ConfigEntry = ConfigEntry
    config_entries.ConfigFlow = ConfigFlow
    ha.config_entries = config_entries

    core = _ensure_module("homeassistant.core")
    core.HomeAssistant = object

    flow = _ensure_module("homeassistant.data_entry_flow")
    flow.FlowResult = dict

    const = _ensure_module("homeassistant.const")

    class Platform:
        SENSOR = "sensor"
        BINARY_SENSOR = "binary_sensor"

    const.Platform = Platform

    helpers = _ensure_module("homeassistant.helpers")
    helpers.__path__ = []
    selector = _ensure_module("homeassistant.helpers.selector")

    class NumberSelectorMode:
        BOX = "box"

    def _number_selector_config(**kwargs):
        return kwargs

    def _number_selector(config):
        return config

    selector.NumberSelectorMode = NumberSelectorMode
    selector.NumberSelectorConfig = _number_selector_config
    selector.NumberSelector = _number_selector
    helpers.selector = selector

    update_coordinator = _ensure_module("homeassistant.helpers.update_coordinator")

    class UpdateFailed(Exception):
        pass

    class DataUpdateCoordinator:
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, hass, logger, *, name, update_interval, config_entry=None):
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
            self.config_entry = config_entry

        async def async_config_entry_first_refresh(self):
            return None

    update_coordinator.UpdateFailed = UpdateFailed
    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator

    voluptuous = _ensure_module("voluptuous")

    def _required(key, default=None):
        return ("required", key, default)

    class _Schema:
        def __init__(self, schema):
            self.schema = schema

    voluptuous.Required = _required
    voluptuous.Schema = _Schema

    smbus2 = _ensure_module("smbus2")
    smbus2.SMBus = factory


def _import_component():
    # Parent package is a namespace; pre-seeding it avoids executing anything
    # before the integration package, whose __init__ imports Home Assistant.
    custom_components = _ensure_module("custom_components")
    custom_components.__path__ = [str(ROOT / "custom_components")]
    custom_components.__package__ = "custom_components"

    sys.modules.pop("custom_components.waveshare_ups_hat", None)
    for name in list(sys.modules):
        if name.startswith("custom_components.waveshare_ups_hat."):
            sys.modules.pop(name)

    import custom_components.waveshare_ups_hat as integration
    from custom_components.waveshare_ups_hat import config_flow, coordinator

    return integration, config_flow, coordinator


@pytest.fixture(scope="module")
def component():
    factory = BusFactory()
    _install_stubs(factory)
    integration, config_flow, coordinator = _import_component()
    return integration, config_flow, coordinator, factory


@pytest.fixture()
def env(component):
    integration, config_flow, coordinator, factory = component
    factory.reset()
    hass = _Hass(factory)
    yield integration, config_flow, coordinator, factory, hass


def _run(coro):
    return asyncio.run(coro)


def test_coordinator_init_does_not_open_the_bus(env):
    _integration, _config_flow, coordinator, factory, hass = env
    coordinator.WaveshareUpsCoordinator(hass, _Entry())
    assert factory.buses == []


def test_setup_opens_in_executor_and_unload_closes(env):
    integration, _config_flow, _coordinator, factory, hass = env
    entry = _Entry()

    assert _run(integration.async_setup_entry(hass, entry)) is True
    assert hass.jobs == ["open_bus"]
    assert [bus.bus_no for bus in factory.buses] == [1]
    assert factory.buses[0].close_calls == 0
    assert entry.entry_id in hass.data["waveshare_ups_hat"]
    assert hass.config_entries.forwarded

    assert _run(integration.async_unload_entry(hass, entry)) is True
    assert hass.jobs == ["open_bus", "close_bus"]
    assert factory.buses[0].close_calls == 1
    assert entry.entry_id not in hass.data["waveshare_ups_hat"]


def test_missing_bus_raises_config_entry_not_ready(env):
    integration, _config_flow, _coordinator, factory, hass = env
    factory.init_error = FileNotFoundError(
        2, "No such file or directory", "/dev/i2c-1"
    )
    with pytest.raises(integration.ConfigEntryNotReady) as raised:
        _run(integration.async_setup_entry(hass, _Entry()))

    assert isinstance(raised.value.__cause__, FileNotFoundError)
    assert "I2C bus 1" in str(raised.value)
    assert factory.buses == []
    assert "waveshare_ups_hat" not in hass.data or hass.data["waveshare_ups_hat"] == {}


def test_failed_first_refresh_closes_the_bus(env):
    integration, _config_flow, coordinator, factory, hass = env

    async def fail(self):
        raise RuntimeError("device nack")

    original = coordinator.WaveshareUpsCoordinator.async_config_entry_first_refresh
    coordinator.WaveshareUpsCoordinator.async_config_entry_first_refresh = fail
    try:
        with pytest.raises(RuntimeError, match="device nack"):
            _run(integration.async_setup_entry(hass, _Entry()))
    finally:
        coordinator.WaveshareUpsCoordinator.async_config_entry_first_refresh = original

    assert factory.buses[0].close_calls == 1
    assert hass.data["waveshare_ups_hat"] == {}


def test_failed_unload_leaves_the_bus_open(env):
    integration, _config_flow, _coordinator, factory, hass = env
    entry = _Entry()
    assert _run(integration.async_setup_entry(hass, entry)) is True
    hass.config_entries.unload_result = False

    assert _run(integration.async_unload_entry(hass, entry)) is False
    assert factory.buses[0].close_calls == 0
    assert entry.entry_id in hass.data["waveshare_ups_hat"]


def test_update_opens_the_bus_in_the_executor(env):
    _integration, _config_flow, coordinator, factory, hass = env
    coord = coordinator.WaveshareUpsCoordinator(hass, _Entry(addr=0x2D))
    factory.read_error = OSError("nack")

    with pytest.raises(coordinator.UpdateFailed, match="0x2d"):
        _run(coord._async_update_data())

    assert hass.jobs == ["read"]
    assert len(factory.buses) == 1
    assert factory.buses[0].close_calls == 0


def test_invalid_address_shows_form_error_without_opening_the_bus(env):
    _integration, config_flow, _coordinator, factory, hass = env
    flow = config_flow.WaveshareUpsConfigFlow()
    flow.hass = hass

    for raw in ("abc", "", "0x", "nope"):
        factory.reset()
        hass.jobs.clear()
        result = _run(
            flow.async_step_user(
                {config_flow.CONF_BUS: 1, config_flow.CONF_ADDR: raw}
            )
        )
        assert result["type"] == "form"
        assert result["errors"] == {"addr": "invalid_address"}
        assert flow.unique_id is None
        assert factory.buses == []
        assert hass.jobs == []


def test_valid_address_probes_in_the_executor_and_closes(env):
    _integration, config_flow, _coordinator, factory, hass = env
    flow = config_flow.WaveshareUpsConfigFlow()
    flow.hass = hass

    result = _run(
        flow.async_step_user({config_flow.CONF_BUS: 1, config_flow.CONF_ADDR: "0x2d"})
    )
    assert result == {
        "type": "create_entry",
        "title": "UPS",
        "data": {"bus": 1, "addr": 0x2D},
    }
    assert hass.jobs == ["_probe"]
    assert factory.buses[0].close_calls == 1
    assert flow.unique_id == "e_1_2d"


def test_probe_failure_is_cannot_connect_and_closes_the_bus(env):
    _integration, config_flow, _coordinator, factory, hass = env
    flow = config_flow.WaveshareUpsConfigFlow()
    flow.hass = hass
    factory.read_error = OSError("remote I/O error")

    result = _run(
        flow.async_step_user({config_flow.CONF_BUS: 1, config_flow.CONF_ADDR: "45"})
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}
    assert factory.buses[0].close_calls == 1


def test_missing_bus_during_probe_is_cannot_connect(env):
    _integration, config_flow, _coordinator, factory, hass = env
    flow = config_flow.WaveshareUpsConfigFlow()
    flow.hass = hass
    factory.init_error = FileNotFoundError(2, "No such file or directory")

    result = _run(
        flow.async_step_user(
            {config_flow.CONF_BUS: 1, config_flow.CONF_ADDR: "  0x2D "}
        )
    )
    assert result["errors"] == {"base": "cannot_connect"}
    assert factory.buses == []
    assert flow.unique_id == "e_1_2d"


def test_unexpected_probe_error_still_closes_the_bus(env):
    _integration, config_flow, _coordinator, factory, hass = env
    flow = config_flow.WaveshareUpsConfigFlow()
    flow.hass = hass
    factory.read_error = RuntimeError("boom")

    result = _run(
        flow.async_step_user({config_flow.CONF_BUS: 1, config_flow.CONF_ADDR: "45"})
    )
    assert result["errors"] == {"base": "unknown"}
    assert factory.buses[0].close_calls == 1


def test_strings_include_invalid_address():
    strings = json.loads((COMPONENT / "strings.json").read_text())
    english = json.loads((COMPONENT / "translations" / "en.json").read_text())
    assert strings == english
    message = strings["config"]["error"]["invalid_address"]
    assert "0x2d" in message
    assert "45" in message
