from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
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
            PowershopEnergyTotalIncreasingSensor(coordinator, entry),
            PowershopUsageKwhSensor(coordinator, entry),
            PowershopUsageTodayKwhSensor(coordinator, entry),
            PowershopUsageYesterdayKwhSensor(coordinator, entry),
            PowershopUsageWeekToDateKwhSensor(coordinator, entry),
            PowershopUsageMonthToDateKwhSensor(coordinator, entry),
            PowershopUsageRolling30dKwhSensor(coordinator, entry),
            PowershopCostWindowSensor(coordinator, entry),
            PowershopCostLastRecordSensor(coordinator, entry),
            PowershopCostMonthToDateSensor(coordinator, entry),
        ]
    )


def _last_record_date(records) -> Optional[date]:
    if not records:
        return None
    last = records[-1]
    return getattr(last, "when", None)


def _sum_kwh(records, start: date, end_inclusive: date) -> Optional[float]:
    vals = [
        r.kwh
        for r in records
        if getattr(r, "kwh", None) is not None and start <= r.when <= end_inclusive
    ]
    return float(sum(vals)) if vals else None


def _sum_cost(records, start: date, end_inclusive: date) -> Optional[float]:
    vals = [
        r.cost_nzd
        for r in records
        if getattr(r, "cost_nzd", None) is not None and start <= r.when <= end_inclusive
    ]
    return float(sum(vals)) if vals else None


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


class PowershopEnergyTotalIncreasingSensor(PowershopBaseSensor, RestoreEntity):
    """
    Cumulative kWh sensor (total_increasing) for Home Assistant Energy dashboard.

    We only have day-level totals from the provider, not a true meter register.
    This sensor persists a running total and increments it when new daily records
    appear (based on record date).
    """

    _attr_name = "Energy total (since install)"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "kWh"

    def __init__(self, coordinator: PowershopCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._total_kwh: Optional[float] = None
        self._last_date: Optional[date] = None

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_energy_total_increasing_kwh"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            try:
                self._total_kwh = float(last_state.state)
            except ValueError:
                self._total_kwh = None
            last_date_str = (last_state.attributes or {}).get("last_record_date")
            if last_date_str:
                try:
                    self._last_date = date.fromisoformat(last_date_str)
                except ValueError:
                    self._last_date = None

        # If nothing restored, initialize from current window so it's non-zero and useful.
        if self._total_kwh is None:
            records = self.coordinator.data.usage_records or []
            vals = [r.kwh for r in records if getattr(r, "kwh", None) is not None]
            self._total_kwh = float(sum(vals)) if vals else 0.0
            self._last_date = _last_record_date(records)

    def _handle_coordinator_update(self) -> None:
        records = self.coordinator.data.usage_records or []
        if not records:
            return super()._handle_coordinator_update()

        # Ensure initialized
        if self._total_kwh is None:
            vals = [r.kwh for r in records if getattr(r, "kwh", None) is not None]
            self._total_kwh = float(sum(vals)) if vals else 0.0
            self._last_date = _last_record_date(records)
            return super()._handle_coordinator_update()

        last_date = self._last_date
        # Increment for new dates only
        for r in records:
            if getattr(r, "kwh", None) is None:
                continue
            if last_date is not None and r.when <= last_date:
                continue
            self._total_kwh += float(r.kwh)
            last_date = r.when

        self._last_date = last_date
        return super()._handle_coordinator_update()

    @property
    def native_value(self) -> Optional[float]:
        return self._total_kwh

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        if self._last_date:
            attrs["last_record_date"] = self._last_date.isoformat()
        return attrs


class PowershopUsageKwhSensor(PowershopBaseSensor):
    _attr_name = "Usage (window)"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
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
    _attr_state_class = SensorStateClass.TOTAL
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
    _attr_state_class = SensorStateClass.TOTAL
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


class PowershopUsageWeekToDateKwhSensor(PowershopBaseSensor):
    _attr_name = "Usage (week to date)"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "kWh"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_usage_wtd_kwh"

    @property
    def native_value(self) -> Optional[float]:
        records = self.coordinator.data.usage_records or []
        last_day = _last_record_date(records)
        if not last_day:
            return None
        start = last_day - timedelta(days=last_day.weekday())  # Monday
        return _sum_kwh(records, start, last_day)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        records = self.coordinator.data.usage_records or []
        last_day = _last_record_date(records)
        if not last_day:
            return {}
        start = last_day - timedelta(days=last_day.weekday())
        return {"from": start.isoformat(), "to": last_day.isoformat()}


class PowershopUsageMonthToDateKwhSensor(PowershopBaseSensor):
    _attr_name = "Usage (month to date)"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "kWh"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_usage_mtd_kwh"

    @property
    def native_value(self) -> Optional[float]:
        records = self.coordinator.data.usage_records or []
        last_day = _last_record_date(records)
        if not last_day:
            return None
        start = last_day.replace(day=1)
        return _sum_kwh(records, start, last_day)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        records = self.coordinator.data.usage_records or []
        last_day = _last_record_date(records)
        if not last_day:
            return {}
        start = last_day.replace(day=1)
        return {"from": start.isoformat(), "to": last_day.isoformat()}


class PowershopUsageRolling30dKwhSensor(PowershopBaseSensor):
    _attr_name = "Usage (rolling 30d)"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "kWh"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_usage_rolling_30d_kwh"

    @property
    def native_value(self) -> Optional[float]:
        records = self.coordinator.data.usage_records or []
        last_day = _last_record_date(records)
        if not last_day:
            return None
        start = last_day - timedelta(days=29)
        return _sum_kwh(records, start, last_day)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        records = self.coordinator.data.usage_records or []
        last_day = _last_record_date(records)
        if not last_day:
            return {}
        start = last_day - timedelta(days=29)
        return {"from": start.isoformat(), "to": last_day.isoformat()}


class PowershopCostMonthToDateSensor(PowershopBaseSensor):
    _attr_name = "Estimated cost (month to date)"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "NZD"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_cost_mtd_nzd"

    @property
    def native_value(self) -> Optional[float]:
        records = self.coordinator.data.usage_records or []
        last_day = _last_record_date(records)
        if not last_day:
            return None
        start = last_day.replace(day=1)
        return _sum_cost(records, start, last_day)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        records = self.coordinator.data.usage_records or []
        last_day = _last_record_date(records)
        if not last_day:
            return {}
        start = last_day.replace(day=1)
        return {"from": start.isoformat(), "to": last_day.isoformat()}

