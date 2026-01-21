from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import PowershopAuthError, PowershopClient, PowershopError
from .const import DEFAULT_USAGE_DAYS, DEFAULT_USAGE_SCALE

_LOGGER = logging.getLogger(__name__)


@dataclass
class PowershopData:
    balance_nzd: float
    usage_records: list


class PowershopCoordinator(DataUpdateCoordinator[PowershopData]):
    def __init__(
        self,
        hass: HomeAssistant,
        *,
        cookie: Optional[str],
        email: Optional[str],
        password: Optional[str],
        customer_id: Optional[str],
        consumer_id: Optional[str],
        usage_scale: str = DEFAULT_USAGE_SCALE,
        usage_days: int = DEFAULT_USAGE_DAYS,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="powershop_nz",
            update_interval=update_interval,
        )
        self._cookie = cookie
        self._email = email
        self._password = password
        self._customer_id = customer_id
        self._consumer_id = consumer_id
        self._usage_scale = usage_scale
        self._usage_days = usage_days

        self._client = PowershopClient(
            session=async_get_clientsession(hass),
            cookie=cookie,
            email=email,
            password=password,
            customer_id=customer_id,
            consumer_id=consumer_id,
        )

    async def _async_update_data(self) -> PowershopData:
        try:
            await self._client.login_if_needed()
            balance = await self._client.fetch_balance_nzd(customer_id=self._customer_id)
            usage = await self._client.fetch_usage_records(
                customer_id=self._customer_id,
                consumer_id=self._consumer_id,
                scale=self._usage_scale,
                days=self._usage_days,
            )
            return PowershopData(balance_nzd=balance, usage_records=usage)
        except PowershopAuthError as e:
            raise UpdateFailed(f"Auth failed: {e}") from e
        except PowershopError as e:
            raise UpdateFailed(str(e)) from e
        except Exception as e:
            raise UpdateFailed(f"Unexpected error: {e}") from e

