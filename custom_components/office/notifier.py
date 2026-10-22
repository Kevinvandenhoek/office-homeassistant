"""The pushes of this house: what changed at the colleagues, and the morning reminder.

What was seen lives in .storage/office.seen, so a restart neither misses a change nor sends one again.
"""

from __future__ import annotations

from datetime import time, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import planner
from .const import CONF_MORNING, CONF_NOTIFY, CONF_PHONE, CONF_UNTIL, DEFAULTS, SEEN_STORE, TITLE
from .coordinator import OfficeCoordinator

_LOGGER = logging.getLogger(__name__)


def option(entry: ConfigEntry, key: str):
    return entry.options.get(key, DEFAULTS[key])


class Notifier:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, coordinator: OfficeCoordinator) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self._store: Store[dict] = Store(hass, 1, f"{SEEN_STORE}.{entry.entry_id}")
        self._data: dict = {}

    async def async_start(self) -> None:
        self._data = await self._store.async_load() or {}
        self.entry.async_on_unload(self.coordinator.async_add_listener(self._updated))
        self.entry.async_on_unload(async_track_time_interval(self.hass, self._tick, timedelta(minutes=1)))
        self._updated()

    @callback
    def _updated(self) -> None:
        data = self.coordinator.data
        if not data or not self.coordinator.last_update_success:
            return
        now = planner.colleagues(data)
        seen = self._data.get("seen")
        self._data["seen"] = now
        self._save()
        # The first look is the start: nothing to compare with.
        if seen is None:
            return
        today = dt_util.now().date()
        clock = dt_util.now().time()
        until = time.fromisoformat(option(self.entry, CONF_UNTIL))
        names = data.get("members", {})
        for change in planner.changes(seen, now, today):
            if planner.should_notify(change, today, clock, until):
                self._send(planner.message(change, names.get(change.member, change.member), today))

    @callback
    def _tick(self, _now=None) -> None:
        now = dt_util.now()
        data = self.coordinator.data
        if not data or not self.coordinator.last_update_success or now.date().isoformat() not in data.get("days", []):
            return
        if not planner.due(time.fromisoformat(option(self.entry, CONF_MORNING)), now, self._data.get("morning")):
            return
        self._data["morning"] = now.date().isoformat()
        self._save()
        names = planner.skipping_today(data, now.date())
        if names:
            self._send(planner.morning_message(names))

    def _send(self, message: str) -> None:
        phone = option(self.entry, CONF_PHONE)
        if not option(self.entry, CONF_NOTIFY) or not phone:
            return
        domain, _, service = phone.partition(".")
        if not self.hass.services.has_service(domain, service):
            _LOGGER.warning("office: %s does not exist, no push for: %s", phone, message)
            return
        self.hass.async_create_task(
            self.hass.services.async_call(domain, service, {"title": TITLE, "message": message}, blocking=False)
        )

    def _save(self) -> None:
        self._store.async_delay_save(lambda: self._data, 1)
