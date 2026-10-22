"""Skip day: your own skip day today; and the switch for the pushes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CONF_NOTIFY
from .entity import OfficeEntity, OfficeSetting


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    add([SkipDaySwitch(entry.runtime_data, "skip_day"), NotifySwitch(entry, "skip_day_notifications", CONF_NOTIFY)])


class SkipDaySwitch(OfficeEntity, SwitchEntity):
    _attr_icon = "mdi:briefcase-off-outline"

    @property
    def available(self) -> bool:
        return super().available and self.today in (self.coordinator.data or {}).get("days", [])

    @property
    def is_on(self) -> bool:
        return self.today in (self.coordinator.data or {}).get("mine", [])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        until = (self.coordinator.data or {}).get("pending", {}).get(self.today)
        return {"pending_until": dt_util.as_local(datetime.fromtimestamp(until, dt_util.UTC)).isoformat() if until else None}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.set_skip(self.today, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.set_skip(self.today, False)


class NotifySwitch(OfficeSetting, SwitchEntity):
    _attr_icon = "mdi:bell-outline"

    @property
    def is_on(self) -> bool:
        return bool(self.value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.set(False)
