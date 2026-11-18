"""Data update coordinator for Ronghao Gas."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    RonghaoGasApi,
    RonghaoGasApiError,
    RonghaoGasAuthError,
    RonghaoGasConfig,
)
from .const import (
    CONF_AES_KEY,
    CONF_API_BASE_URL,
    CONF_BEARER_TOKEN,
    CONF_SCAN_INTERVAL_HOURS,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_USER_ID,
    CONF_USERFILES_ID,
    CONF_USERINFO_ID,
    DEFAULT_API_BASE_URL,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
    SCAN_INTERVAL_HOUR_OPTIONS,
)

_LOGGER = logging.getLogger(__name__)


class RonghaoGasDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate all Ronghao Gas sensor updates."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        data = entry.data
        interval_hours = _scan_interval_hours(entry)
        config = RonghaoGasConfig(
            api_base_url=data.get(CONF_API_BASE_URL, DEFAULT_API_BASE_URL),
            bearer_token=data[CONF_BEARER_TOKEN],
            aes_key=data[CONF_AES_KEY],
            user_id=data[CONF_USER_ID],
            userfiles_id=data[CONF_USERFILES_ID],
            userinfo_id=data[CONF_USERINFO_ID],
        )
        self.api = RonghaoGasApi(async_get_clientsession(hass), config)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(hours=interval_hours),
            always_update=False,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest data from Ronghao Gas."""
        try:
            return await self.api.async_fetch_all()
        except RonghaoGasAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except RonghaoGasApiError as err:
            raise UpdateFailed(str(err)) from err


def _scan_interval_hours(entry: ConfigEntry) -> int:
    """Return configured poll interval in hours."""
    value = entry.options.get(CONF_SCAN_INTERVAL_HOURS)
    if value is None and (old_minutes := entry.data.get(CONF_SCAN_INTERVAL_MINUTES)):
        try:
            value = round(int(old_minutes) / 60)
        except (TypeError, ValueError):
            value = None

    try:
        hours = int(value) if value is not None else DEFAULT_SCAN_INTERVAL_HOURS
    except (TypeError, ValueError):
        hours = DEFAULT_SCAN_INTERVAL_HOURS

    return hours if hours in SCAN_INTERVAL_HOUR_OPTIONS else DEFAULT_SCAN_INTERVAL_HOURS
