"""Ronghao Gas integration."""

from __future__ import annotations

import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .const import (
    ATTR_ENTRY_ID,
    DATA_COORDINATORS,
    DOMAIN,
    PLATFORMS,
    SERVICE_REFRESH,
)
from .coordinator import RonghaoGasDataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ronghao Gas from a config entry."""
    coordinator = RonghaoGasDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    domain_data = hass.data.setdefault(DOMAIN, {DATA_COORDINATORS: {}})
    domain_data.setdefault(DATA_COORDINATORS, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinators = hass.data.get(DOMAIN, {}).get(DATA_COORDINATORS, {})
        coordinators.pop(entry.entry_id, None)
        if not coordinators and hass.services.has_service(DOMAIN, SERVICE_REFRESH):
            hass.services.async_remove(DOMAIN, SERVICE_REFRESH)
            hass.data.pop(DOMAIN, None)
    return unload_ok


def _register_services(hass: HomeAssistant) -> None:
    """Register integration services once."""
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        return

    async def async_refresh(call: ServiceCall) -> None:
        """Refresh one or all Ronghao Gas config entries."""
        coordinators = hass.data.get(DOMAIN, {}).get(DATA_COORDINATORS, {})
        entry_id = call.data.get(ATTR_ENTRY_ID)

        if entry_id:
            coordinator = coordinators.get(entry_id)
            if coordinator is None:
                raise HomeAssistantError(f"Ronghao Gas entry not found: {entry_id}")
            await coordinator.async_request_refresh()
            return

        await asyncio.gather(
            *(coordinator.async_request_refresh() for coordinator in coordinators.values())
        )

    hass.services.async_register(DOMAIN, SERVICE_REFRESH, async_refresh)
