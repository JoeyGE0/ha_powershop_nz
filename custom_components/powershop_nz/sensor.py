from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Any, Optional

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PowershopCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PowershopCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            PowershopBalanceSensor(coordinator, entry),
            PowershopUsageKwhSensor(coordinator, entry),
        ]
    )


class PowershopBaseSensor(CoordinatorEntity[PowershopCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: PowershopCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry


class PowershopBalanceSensor(PowershopBaseSensor):
    _attr_name = "Balance"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "NZD"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_balance"

    @property
    def native_value(self) -> float:
        return float(self.coordinator.data.balance_nzd)


class PowershopUsageKwhSensor(PowershopBaseSensor):
    _attr_name = "Usage (window)"
    _attr_native_unit_of_measurement = "kWh"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_usage_kwh"

    @property
    def native_value(self) -> Optional[float]:
        records = self.coordinator.data.usage_records or []
        # sum available kWh values
        vals = [r.kwh for r in records if getattr(r, "kwh", None) is not None]
        if not vals:
            return None
        return float(sum(vals))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        records = self.coordinator.data.usage_records or []
        last = records[-1] if records else None
        attrs: dict[str, Any] = {
            "records_count": len(records),
        }
        if last:
            attrs["last_record_date"] = last.when.isoformat()
            if last.cost_nzd is not None:
                attrs["last_record_cost_nzd"] = last.cost_nzd
        return attrs

