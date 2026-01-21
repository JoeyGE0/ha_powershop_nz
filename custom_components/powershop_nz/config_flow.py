from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .client import PowershopClient, PowershopError
from .const import (
    CONF_CONSUMER_ID,
    CONF_COOKIE,
    CONF_CUSTOMER_ID,
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
                    session=self.hass.helpers.aiohttp_client.async_get_clientsession(self.hass),
                    cookie=cookie or None,
                    email=email or None,
                    password=password or None,
                    customer_id=user_input.get(CONF_CUSTOMER_ID) or None,
                    consumer_id=user_input.get(CONF_CONSUMER_ID) or None,
                )
                await client.login_if_needed()
                # Smoke test: fetch balance
                _ = await client.fetch_balance_nzd(customer_id=client.customer_id)
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                title = "Powershop NZ"
                return self.async_create_entry(title=title, data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(CONF_COOKIE): str,
                vol.Optional(CONF_EMAIL): str,
                vol.Optional(CONF_PASSWORD): str,
                vol.Optional(CONF_CUSTOMER_ID): str,
                vol.Optional(CONF_CONSUMER_ID): str,
                vol.Optional(CONF_USAGE_SCALE, default=DEFAULT_USAGE_SCALE): vol.In(
                    ["day", "week", "month", "billing"]
                ),
                vol.Optional(CONF_USAGE_DAYS, default=DEFAULT_USAGE_DAYS): vol.Coerce(int),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

