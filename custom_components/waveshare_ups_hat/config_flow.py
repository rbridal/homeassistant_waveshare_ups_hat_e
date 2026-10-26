"""Config flow for Waveshare UPS HAT (E)."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import CONF_ADDR, CONF_BUS, DEFAULT_ADDR, DEFAULT_BUS, DEFAULT_NAME, DOMAIN
from .ups_hat_e import parse_i2c_address, probe_device


def _box_number(
    *,
    min_value: float | None = None,
    max_value: float | None = None,
    step: float = 1,
) -> selector.NumberSelector:
    """Number field rendered as a text box (not a slider)."""
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=min_value,
            max=max_value,
            step=step,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


async def _async_validate_i2c(hass: HomeAssistant, bus: int, addr: int) -> str | None:
    """Try a quick I2C read; return error key or None on success."""

    def _probe() -> None:
        # probe_device closes the bus even when the read fails.
        probe_device(bus, addr)

    try:
        await hass.async_add_executor_job(_probe)
    except OSError:
        return "cannot_connect"
    except Exception:  # noqa: BLE001 - surface unexpected probe failures
        return "unknown"
    return None


class WaveshareUpsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Waveshare UPS HAT (E)."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Collect I2C bus and address.

        Device name/area are handled by HA's standard "Name and assign" step
        after the entry is created (default title: UPS).
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            bus = int(user_input[CONF_BUS])
            try:
                addr = parse_i2c_address(user_input[CONF_ADDR])
            except ValueError:
                errors[CONF_ADDR] = "invalid_address"
            else:
                await self.async_set_unique_id(f"e_{bus}_{addr:02x}")
                self._abort_if_unique_id_configured()

                error = await _async_validate_i2c(self.hass, bus, addr)
                if error:
                    errors["base"] = error
                else:
                    return self.async_create_entry(
                        title=DEFAULT_NAME,
                        data={CONF_BUS: bus, CONF_ADDR: addr},
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BUS, default=DEFAULT_BUS): _box_number(
                        min_value=0, max_value=10, step=1
                    ),
                    vol.Required(CONF_ADDR, default=f"0x{DEFAULT_ADDR:02x}"): str,
                }
            ),
            errors=errors,
        )
