"""Config flow for Ronghao Gas."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    RonghaoGasAesKeyError,
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
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
    SCAN_INTERVAL_HOUR_OPTIONS,
)


class RonghaoGasConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ronghao Gas."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return RonghaoGasOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(str(user_input[CONF_USERINFO_ID]))
            self._abort_if_unique_id_configured()

            try:
                await _validate_input(self.hass, user_input)
            except RonghaoGasAesKeyError:
                errors["base"] = "invalid_aes_key"
            except RonghaoGasAuthError:
                errors["base"] = "invalid_auth"
            except RonghaoGasApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                title = f"{DEFAULT_NAME} {user_input[CONF_USER_ID]}"
                return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_data_schema(user_input),
            errors=errors,
        )


async def _validate_input(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate user input by fetching data once."""
    config = RonghaoGasConfig(
        api_base_url=data.get(CONF_API_BASE_URL, DEFAULT_API_BASE_URL),
        bearer_token=data[CONF_BEARER_TOKEN],
        aes_key=data[CONF_AES_KEY],
        user_id=str(data[CONF_USER_ID]),
        userfiles_id=str(data[CONF_USERFILES_ID]),
        userinfo_id=str(data[CONF_USERINFO_ID]),
    )
    api = RonghaoGasApi(async_get_clientsession(hass), config)
    await api.async_validate()


def _data_schema(user_input: dict[str, Any] | None = None) -> vol.Schema:
    """Return the setup form schema."""
    suggested = user_input or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_BEARER_TOKEN, default=suggested.get(CONF_BEARER_TOKEN, "")
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_USER_ID, default=suggested.get(CONF_USER_ID, "")): str,
            vol.Required(
                CONF_USERFILES_ID, default=suggested.get(CONF_USERFILES_ID, "")
            ): str,
            vol.Required(
                CONF_USERINFO_ID, default=suggested.get(CONF_USERINFO_ID, "")
            ): str,
            vol.Optional(
                CONF_API_BASE_URL,
                default=suggested.get(CONF_API_BASE_URL, DEFAULT_API_BASE_URL),
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
            ),
            vol.Required(
                CONF_AES_KEY, default=suggested.get(CONF_AES_KEY, "")
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        }
    )


class RonghaoGasOptionsFlow(config_entries.OptionsFlowWithReload):
    """Handle Ronghao Gas options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL_HOURS: int(user_input[CONF_SCAN_INTERVAL_HOURS])
                }
            )

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(self.config_entry),
        )


def _options_schema(config_entry: config_entries.ConfigEntry) -> vol.Schema:
    """Return the options schema."""
    current = _current_scan_interval_hours(config_entry)
    return vol.Schema(
        {
            vol.Required(CONF_SCAN_INTERVAL_HOURS, default=str(current)): (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=str(hours), label=f"每{hours}小时"
                            )
                            for hours in SCAN_INTERVAL_HOUR_OPTIONS
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            )
        }
    )


def _current_scan_interval_hours(config_entry: config_entries.ConfigEntry) -> int:
    """Return current interval, including migration from the old minute setting."""
    option_value = config_entry.options.get(CONF_SCAN_INTERVAL_HOURS)
    if option_value is not None:
        return _normalize_interval_hours(option_value)

    old_minutes = config_entry.data.get(CONF_SCAN_INTERVAL_MINUTES)
    if old_minutes is not None:
        try:
            return _normalize_interval_hours(round(int(old_minutes) / 60))
        except (TypeError, ValueError):
            pass

    return DEFAULT_SCAN_INTERVAL_HOURS


def _normalize_interval_hours(value: Any) -> int:
    """Return an allowed interval hour value."""
    try:
        hours = int(value)
    except (TypeError, ValueError):
        return DEFAULT_SCAN_INTERVAL_HOURS
    return hours if hours in SCAN_INTERVAL_HOUR_OPTIONS else DEFAULT_SCAN_INTERVAL_HOURS
