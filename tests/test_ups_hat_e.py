"""UPS HAT (E) bus lifecycle and address parsing. No Home Assistant runtime."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

DRIVER_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "waveshare_ups_hat"
    / "ups_hat_e.py"
)


class FakeBus:
    """Stand-in for smbus2.SMBus."""

    def __init__(self, bus_no: int, factory: BusFactory) -> None:
        self.bus_no = bus_no
        self.factory = factory
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1

    def read_i2c_block_data(self, addr: int, register: int, length: int) -> list[int]:
        if self.factory.read_error is not None:
            raise self.factory.read_error
        assert addr == 0x2D
        if register == 0x02:
            assert length == 1
            return [0x80]  # charging
        if register == 0x10:
            assert length == 6
            return [0x98, 0x3A, 0x64, 0x00, 0x10, 0x00]  # 15000 mV
        if register == 0x20:
            assert length == 12
            return [
                0x80,
                0x3E,  # 16000 mV
                0xF4,
                0x01,  # 500 mA
                80,
                0x00,
                0xD0,
                0x07,  # 2000 mAh
                0xFF,
                0xFF,
                60,
                0x00,
            ]
        if register == 0x30:
            assert length == 8
            return [0x10, 0x0E] * 4
        raise AssertionError(f"unexpected register 0x{register:02x}")


class BusFactory:
    """SMBus stand-in that records opens and can fail on demand."""

    def __init__(self) -> None:
        self.buses: list[FakeBus] = []
        self.init_error: BaseException | None = None
        self.read_error: BaseException | None = None

    def __call__(self, bus_no: int) -> FakeBus:
        if self.init_error is not None:
            raise self.init_error
        bus = FakeBus(bus_no, self)
        self.buses.append(bus)
        return bus


def _load_driver(factory: BusFactory):
    smbus2 = types.ModuleType("smbus2")
    smbus2.SMBus = factory
    sys.modules["smbus2"] = smbus2
    spec = importlib.util.spec_from_file_location("ups_hat_e_under_test", DRIVER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def driver():
    previous = sys.modules.get("smbus2")
    factory = BusFactory()
    module = _load_driver(factory)
    yield module, factory
    if previous is None:
        sys.modules.pop("smbus2", None)
    else:
        sys.modules["smbus2"] = previous


def test_constructor_does_not_open_the_bus(driver):
    module, factory = driver
    module.UPSHatE(i2c_bus=1, addr=0x2D)
    assert factory.buses == []


def test_open_and_read_are_lazy_and_parse_registers(driver):
    module, factory = driver
    ups = module.UPSHatE(i2c_bus=1, addr=0x2D)
    data = ups.read()
    assert [bus.bus_no for bus in factory.buses] == [1]
    assert data["status"] == "charging"
    assert data["is_charging"] is True
    assert data["vbus_voltage"] == 15000
    assert data["battery_voltage"] == 16000
    assert data["battery_current"] == 500
    assert data["battery_percent"] == 80
    assert data["time_to_empty"] is None
    assert data["time_to_full"] == 60

    ups.read()
    assert len(factory.buses) == 1  # already open


def test_open_oserror_is_raised_and_close_is_safe(driver):
    module, factory = driver
    factory.init_error = FileNotFoundError(2, "No such file or directory", "/dev/i2c-4")
    ups = module.UPSHatE(i2c_bus=4, addr=0x2D)
    with pytest.raises(FileNotFoundError):
        ups.open()
    ups.close()
    assert factory.buses == []


def test_close_releases_the_handle_once(driver):
    module, factory = driver
    ups = module.UPSHatE(i2c_bus=1, addr=0x2D)
    ups.open()
    ups.close()
    ups.close()
    assert factory.buses[0].close_calls == 1


def test_probe_closes_after_success(driver):
    module, factory = driver
    data = module.probe_device(1, 0x2D)
    assert data["vbus_voltage"] == 15000
    assert factory.buses[0].close_calls == 1


def test_probe_closes_when_the_read_fails(driver):
    module, factory = driver
    factory.read_error = OSError("remote I/O error")
    with pytest.raises(OSError, match="remote I/O error"):
        module.probe_device(1, 0x2D)
    assert factory.buses[0].close_calls == 1


def test_probe_closes_when_the_bus_cannot_be_opened(driver):
    module, factory = driver
    factory.init_error = FileNotFoundError(2, "No such file or directory")
    with pytest.raises(FileNotFoundError):
        module.probe_device(2, 0x2D)
    assert factory.buses == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0x2d", 0x2D),
        ("0X2D", 0x2D),
        ("45", 45),
        ("  45 ", 45),
        (45, 45),
    ],
)
def test_parse_i2c_address_accepts_decimal_and_hex(driver, raw, expected):
    module, _factory = driver
    assert module.parse_i2c_address(raw) == expected


@pytest.mark.parametrize("raw", ["abc", "", "   ", "0x", "0x2dxyz", "nope"])
def test_parse_i2c_address_rejects_non_numeric(driver, raw):
    module, _factory = driver
    with pytest.raises(ValueError):
        module.parse_i2c_address(raw)
