"""The time of the morning reminder, and until when a push about today still goes."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_MORNING, CONF_UNTIL
from .entity import OfficeSetting


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    add([
        OfficeTime(entry, "skip_day_morning_reminder", CONF_MORNING, "mdi:alarm"),
        OfficeTime(entry, "skip_day_notify_until", CONF_UNTIL, "mdi:clock-end"),
    ])


class OfficeTime(OfficeSetting, TimeEntity):
    def __init__(self, entry: ConfigEntry, key: str, option: str, icon: str) -> None:
        super().__init__(entry, key, option)
        self._attr_icon = icon

    @property
    def native_value(self) -> time:
        return time.fromisoformat(self.value)

    async def async_set_value(self, value: time) -> None:
        self.set(value.strftime("%H:%M"))
