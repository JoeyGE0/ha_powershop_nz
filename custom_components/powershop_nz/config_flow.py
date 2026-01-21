from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import PowershopClient
from .const import (
    CONF_COOKIE,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_USAGE_DAYS,
    CONF_USAGE_SCALE,
    DEFAULT_USAGE_DAYS,
    DEFAULT_USAGE_SCALE,
    DOMAIN,
)


class PowershopNZConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors = {}

        if user_input is not None:
            cookie = user_input.get(CONF_COOKIE)
            email = user_input.get(CONF_EMAIL)
            password = user_input.get(CONF_PASSWORD)

            try:
                client = PowershopClient(
                    session=async_get_clientsession(self.hass),
                    cookie=cookie or None,
                    email=email or None,
                    password=password or None,
                    customer_id=None,
                    consumer_id=None,
                )
                await client.login_if_needed()
                # Smoke test: fetch balance
                _ = await client.fetch_balance_nzd(customer_id=None)
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                title = "Powershop NZ"
                return self.async_create_entry(title=title, data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
                # Optional fallback if login fails in HA environment:
                vol.Optional(CONF_COOKIE): str,
                # Keep usage settings here but with sane defaults (not a wall of boxes):
                vol.Optional(CONF_USAGE_SCALE, default=DEFAULT_USAGE_SCALE): vol.In(["day", "week", "month", "billing"]),
                vol.Optional(CONF_USAGE_DAYS, default=DEFAULT_USAGE_DAYS): vol.Coerce(int),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry):
        return PowershopNZOptionsFlow(config_entry)


class PowershopNZOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Keep options minimal: usage window & scale only (advanced IDs can be added later if needed)
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_USAGE_SCALE,
                    default=self.config_entry.options.get(CONF_USAGE_SCALE, DEFAULT_USAGE_SCALE),
                ): vol.In(["day", "week", "month", "billing"]),
                vol.Optional(
                    CONF_USAGE_DAYS,
                    default=self.config_entry.options.get(CONF_USAGE_DAYS, DEFAULT_USAGE_DAYS),
                ): vol.Coerce(int),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)

