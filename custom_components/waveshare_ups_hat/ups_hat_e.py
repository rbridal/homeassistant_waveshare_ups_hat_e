"""I2C reader for the Waveshare UPS HAT (E).

Unlike the original UPS HAT / UPS HAT (C) (which use an INA219 current sensor),
the (E) exposes everything through an on-board MCU at I2C address 0x2d.
Register map is taken from Waveshare's official ``ups.py`` demo.
"""
from __future__ import annotations

from typing import Any

try:
    import smbus2 as smbus
except ImportError:  # pragma: no cover - fallback for older images
    import smbus

DEFAULT_ADDR = 0x2D
DEFAULT_BUS = 1

# Sentinel returned by the MCU for a time estimate that does not apply
# (e.g. "time to empty" while the pack is charging).
_NA = 0xFFFF


def parse_i2c_address(value: object) -> int:
    """Parse a decimal or 0x-hex I2C address.

    Raises:
        ValueError: The value is empty or not numeric.
    """
    return int(str(value).strip(), 0)


def _u16(data: list[int], i: int) -> int:
    """Little-endian unsigned 16-bit from a block-read buffer."""
    return data[i] | (data[i + 1] << 8)


def _s16(data: list[int], i: int) -> int:
    """Little-endian signed 16-bit from a block-read buffer."""
    val = _u16(data, i)
    if val > 0x7FFF:
        val -= 0x10000
    return val


class UPSHatE:
    """Raw reader for the UPS HAT (E) MCU.

    Constructing the object does not touch the I2C device. ``open()`` and
    ``read()`` open ``/dev/i2c-*`` and must run in an executor.
    """

    def __init__(self, i2c_bus: int = DEFAULT_BUS, addr: int = DEFAULT_ADDR) -> None:
        self.addr = addr
        self._i2c_bus = i2c_bus
        self._bus: Any | None = None

    def open(self) -> None:
        """Open the I2C bus. Blocking; call from an executor.

        Raises:
            OSError: The bus device does not exist or cannot be opened.
        """
        if self._bus is None:
            self._bus = smbus.SMBus(self._i2c_bus)

    def close(self) -> None:
        """Close the I2C bus if it is open. Blocking; call from an executor."""
        bus = self._bus
        self._bus = None
        if bus is not None:
            bus.close()

    def read(self) -> dict[str, Any]:
        """Read all registers and return a parsed dict (raw units: mV/mA/mW)."""
        self.open()
        bus = self._bus
        if bus is None:  # pragma: no cover - open() assigns the bus or raises
            raise OSError(f"I2C bus {self._i2c_bus} is not open")

        status = bus.read_i2c_block_data(self.addr, 0x02, 0x01)[0]
        if status & 0x40:
            state = "fast_charging"
        elif status & 0x80:
            state = "charging"
        elif status & 0x20:
            state = "discharging"
        else:
            state = "idle"

        vbus = bus.read_i2c_block_data(self.addr, 0x10, 0x06)
        bat = bus.read_i2c_block_data(self.addr, 0x20, 0x0C)
        cells = bus.read_i2c_block_data(self.addr, 0x30, 0x08)

        battery_current = _s16(bat, 2)
        time_to_empty = _u16(bat, 8)
        time_to_full = _u16(bat, 10)

        return {
            "status": state,
            "is_charging": state in ("charging", "fast_charging"),
            "is_discharging": state == "discharging",
            # mains/USB-C present: charging, or simply not running on battery
            "online": state != "discharging",
            "vbus_voltage": _u16(vbus, 0),
            "vbus_current": _u16(vbus, 2),
            "vbus_power": _u16(vbus, 4),
            "battery_voltage": _u16(bat, 0),
            "battery_current": battery_current,
            "battery_percent": _u16(bat, 4),
            "remaining_capacity": _u16(bat, 6),
            # Only the estimate matching the current direction is meaningful;
            # the MCU returns 0xFFFF for the inapplicable one.
            "time_to_empty": None
            if (time_to_empty == _NA or battery_current >= 0)
            else time_to_empty,
            "time_to_full": None
            if (time_to_full == _NA or battery_current < 0)
            else time_to_full,
            "cell_voltage_1": _u16(cells, 0),
            "cell_voltage_2": _u16(cells, 2),
            "cell_voltage_3": _u16(cells, 4),
            "cell_voltage_4": _u16(cells, 6),
        }


def probe_device(i2c_bus: int, addr: int) -> dict[str, Any]:
    """Read the UPS once and always release the I2C file handle."""
    ups = UPSHatE(i2c_bus=i2c_bus, addr=addr)
    try:
        return ups.read()
    finally:
        ups.close()
