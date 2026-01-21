from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CONSUMER_ID,
    CONF_COOKIE,
    CONF_CUSTOMER_ID,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_USAGE_DAYS,
    CONF_USAGE_SCALE,
    DEFAULT_SCAN_INTERVAL_MIN,
    DOMAIN,
)
from .coordinator import PowershopCoordinator


PLATFORMS: list[str] = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = entry.data
    options = entry.options

    cookie = data.get(CONF_COOKIE)
    email = data.get(CONF_EMAIL)
    password = data.get(CONF_PASSWORD)
    customer_id = data.get(CONF_CUSTOMER_ID)
    consumer_id = data.get(CONF_CONSUMER_ID)

    usage_scale = options.get(CONF_USAGE_SCALE, data.get(CONF_USAGE_SCALE))
    usage_days = int(options.get(CONF_USAGE_DAYS, data.get(CONF_USAGE_DAYS, 7)))
    scan_min = int(options.get("scan_interval_min", DEFAULT_SCAN_INTERVAL_MIN))

    coordinator = PowershopCoordinator(
        hass,
        cookie=cookie,
        email=email,
        password=password,
        customer_id=customer_id,
        consumer_id=consumer_id,
        usage_scale=usage_scale,
        usage_days=usage_days,
        update_interval=timedelta(minutes=scan_min),
    )

    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok

