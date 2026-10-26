"""The Waveshare UPS Hat integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import WaveshareUpsCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Waveshare UPS Hat from a config entry."""
    coordinator = WaveshareUpsCoordinator(hass, entry)
    try:
        await hass.async_add_executor_job(coordinator.open_bus)
    except OSError as err:
        raise ConfigEntryNotReady(
            f"Cannot open I2C bus {coordinator.bus}: {err}"
        ) from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    try:
        await coordinator.async_config_entry_first_refresh()
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:  # noqa: BLE001 - close the bus, then re-raise
        # Includes ConfigEntryNotReady from the first refresh. Drop the
        # coordinator and close the bus so a retry does not leak the fd.
        hass.data[DOMAIN].pop(entry.entry_id, None)
        await hass.async_add_executor_job(coordinator.close_bus)
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and close the I2C bus."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: WaveshareUpsCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await hass.async_add_executor_job(coordinator.close_bus)
    return unload_ok
