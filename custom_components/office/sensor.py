"""Skip days: who of the colleagues skips today, and every office day of this and next week in `days`."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import planner
from .entity import OfficeEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    add([SkipDaysSensor(entry.runtime_data, "skip_days")])


class SkipDaysSensor(OfficeEntity, SensorEntity):
    _attr_icon = "mdi:briefcase-clock-outline"

    @property
    def native_value(self) -> str:
        data = self.coordinator.data or {}
        if self.today not in data.get("days", []):
            return "No office today"
        names = planner.skipping_today(data, dt_util.now().date())
        return ", ".join(names) if names else "Nobody"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        names = data.get("members", {})
        others = planner.colleagues(data)
        pending = data.get("pending", {})
        today = dt_util.now().date()
        days = []
        for day in data.get("days", []):
            until = pending.get(day)
            days.append({
                "date": day,
                "name": planner.day_name(day, today),
                "skipping": [names.get(m, m) for m, skips in others.items() if day in skips],
                "mine": day in data.get("mine", []),
                "pending_until": dt_util.as_local(datetime.fromtimestamp(until, dt_util.UTC)).isoformat() if until else None,
            })
        return {
            "me": names.get(data.get("me"), data.get("me")),
            "colleagues": [n for m, n in names.items() if m != data.get("me")],
            "office_days": [planner.WEEKDAYS[d] for d in data.get("office_days", [])],
            "days": days,
        }
