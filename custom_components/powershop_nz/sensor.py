from __future__ import annotations

from typing import Any, Optional

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
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
            PowershopUsageTodayKwhSensor(coordinator, entry),
            PowershopUsageYesterdayKwhSensor(coordinator, entry),
            PowershopCostWindowSensor(coordinator, entry),
            PowershopCostLastRecordSensor(coordinator, entry),
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
    _attr_device_class = SensorDeviceClass.ENERGY
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


class PowershopUsageTodayKwhSensor(PowershopBaseSensor):
    _attr_name = "Usage (today)"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_usage_today_kwh"

    @property
    def native_value(self) -> Optional[float]:
        records = self.coordinator.data.usage_records or []
        if not records:
            return None
        last = records[-1]
        return float(last.kwh) if last.kwh is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        records = self.coordinator.data.usage_records or []
        if not records:
            return {}
        last = records[-1]
        attrs: dict[str, Any] = {"date": last.when.isoformat()}
        if last.cost_nzd is not None:
            attrs["estimated_cost_nzd"] = last.cost_nzd
        return attrs


class PowershopUsageYesterdayKwhSensor(PowershopBaseSensor):
    _attr_name = "Usage (yesterday)"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_usage_yesterday_kwh"

    @property
    def native_value(self) -> Optional[float]:
        records = self.coordinator.data.usage_records or []
        if len(records) < 2:
            return None
        prev = records[-2]
        return float(prev.kwh) if prev.kwh is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        records = self.coordinator.data.usage_records or []
        if len(records) < 2:
            return {}
        prev = records[-2]
        attrs: dict[str, Any] = {"date": prev.when.isoformat()}
        if prev.cost_nzd is not None:
            attrs["estimated_cost_nzd"] = prev.cost_nzd
        return attrs


class PowershopCostWindowSensor(PowershopBaseSensor):
    _attr_name = "Estimated cost (window)"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "NZD"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_cost_window_nzd"

    @property
    def native_value(self) -> Optional[float]:
        records = self.coordinator.data.usage_records or []
        vals = [r.cost_nzd for r in records if getattr(r, "cost_nzd", None) is not None]
        if not vals:
            return None
        return float(sum(vals))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        records = self.coordinator.data.usage_records or []
        return {"records_count": len(records)}


class PowershopCostLastRecordSensor(PowershopBaseSensor):
    _attr_name = "Estimated cost (last record)"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "NZD"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_cost_last_nzd"

    @property
    def native_value(self) -> Optional[float]:
        records = self.coordinator.data.usage_records or []
        if not records:
            return None
        last = records[-1]
        return float(last.cost_nzd) if last.cost_nzd is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        records = self.coordinator.data.usage_records or []
        if not records:
            return {}
        last = records[-1]
        return {"date": last.when.isoformat()}

