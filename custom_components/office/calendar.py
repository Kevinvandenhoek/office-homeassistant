"""Office: everyone's skip days as whole-day events, for calendar cards and anything that reads calendars."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .entity import OfficeEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    add([OfficeCalendar(entry.runtime_data, "office")])


class OfficeCalendar(OfficeEntity, CalendarEntity):
    # The main entity of the device: it takes the device's name, so it is calendar.office.
    _attr_name = None
    _attr_icon = "mdi:briefcase-off-outline"

    def _events(self) -> list[CalendarEvent]:
        data = self.coordinator.data or {}
        names = data.get("members", {})
        events = []
        for member, days in data.get("skips", {}).items():
            for day in days:
                start = date.fromisoformat(day)
                events.append(CalendarEvent(start=start, end=start + timedelta(days=1), summary=f"{names.get(member, member)} skips the office", uid=f"{member}_{day}"))
        return sorted(events, key=lambda e: (e.start, e.summary))

    @property
    def event(self) -> CalendarEvent | None:
        today = self.today
        return next((e for e in self._events() if e.end.isoformat() > today), None)

    async def async_get_events(self, hass: HomeAssistant, start_date: datetime, end_date: datetime) -> list[CalendarEvent]:
        day = dt_util.start_of_local_day
        return [e for e in self._events() if day(e.end) > start_date and day(e.start) < end_date]
