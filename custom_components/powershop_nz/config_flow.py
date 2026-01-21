from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import PowershopClient
from .const import (
    AUTH_METHOD_COOKIE,
    AUTH_METHOD_EMAIL_PASSWORD,
    CONF_AUTH_METHOD,
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
        """Pick auth method first (keeps UI clean and avoids brittle login path)."""
        if user_input is not None:
            method = user_input.get(CONF_AUTH_METHOD)
            if method == AUTH_METHOD_COOKIE:
                return await self.async_step_cookie()
            return await self.async_step_credentials()

        schema = vol.Schema(
            {
                vol.Required(CONF_AUTH_METHOD, default=AUTH_METHOD_EMAIL_PASSWORD): vol.In(
                    [AUTH_METHOD_EMAIL_PASSWORD, AUTH_METHOD_COOKIE]
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_credentials(self, user_input=None) -> FlowResult:
        errors = {}
        if user_input is not None:
            try:
                client = PowershopClient(
                    session=async_get_clientsession(self.hass),
                    cookie=None,
                    email=user_input[CONF_EMAIL],
                    password=user_input[CONF_PASSWORD],
                    customer_id=None,
                    consumer_id=None,
                )
                await client.login_if_needed()
                _ = await client.fetch_balance_nzd(customer_id=None)
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title="Powershop NZ",
                    data={
                        CONF_AUTH_METHOD: AUTH_METHOD_EMAIL_PASSWORD,
                        CONF_EMAIL: user_input[CONF_EMAIL],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )

        schema = vol.Schema({vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str})
        return self.async_show_form(step_id="credentials", data_schema=schema, errors=errors)

    async def async_step_cookie(self, user_input=None) -> FlowResult:
        errors = {}
        if user_input is not None:
            try:
                client = PowershopClient(
                    session=async_get_clientsession(self.hass),
                    cookie=user_input[CONF_COOKIE],
                    email=None,
                    password=None,
                    customer_id=None,
                    consumer_id=None,
                )
                await client.login_if_needed()
                _ = await client.fetch_balance_nzd(customer_id=None)
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title="Powershop NZ",
                    data={
                        CONF_AUTH_METHOD: AUTH_METHOD_COOKIE,
                        CONF_COOKIE: user_input[CONF_COOKIE],
                    },
                )

        schema = vol.Schema({vol.Required(CONF_COOKIE): str})
        return self.async_show_form(step_id="cookie", data_schema=schema, errors=errors)

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

