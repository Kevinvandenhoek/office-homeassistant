"""The host: keeps the members and everyone's skip days, and publishes a change after the grace minute."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import secrets
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import planner
from .const import CONF_NAME, CONF_OFFICE_DAYS, HUB_STORE


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class OfficeHub:
    """Everything lives in .storage/office.hub: {"members": {id: {"name", "token_hash"}}, "skips": {id: {date: record}}}."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.me = planner.member_id(entry.data[CONF_NAME])
        self._store: Store[dict] = Store(hass, 1, HUB_STORE)
        self._data: dict = {"members": {}, "skips": {}}
        self._timer: CALLBACK_TYPE | None = None
        self._listeners: list[Callable[[], None]] = []

    async def async_load(self) -> None:
        self._data = await self._store.async_load() or {"members": {}, "skips": {}}
        self._data["members"].setdefault(self.me, {"name": self.entry.data[CONF_NAME]})
        # A change that waited when Home Assistant stopped is published now, or when its minute is up.
        self._promote()

    @callback
    def async_stop(self) -> None:
        if self._timer:
            self._timer()
            self._timer = None

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @property
    def office_days(self) -> list[int]:
        return self.entry.options.get(CONF_OFFICE_DAYS, planner.DEFAULT_OFFICE_DAYS)

    @property
    def members(self) -> dict[str, str]:
        return {m: v["name"] for m, v in self._data["members"].items()}

    def colleagues(self) -> dict[str, str]:
        return {m: n for m, n in self.members.items() if m != self.me}

    def view(self, member: str) -> dict:
        return planner.view(self.members, self._data["skips"], self.office_days, member, dt_util.now().date())

    def member_for_token(self, token: str) -> str | None:
        """The member of this token; compares every hash, so the time says nothing about which one is close."""
        digest = _hash(token)
        found = None
        for member, value in self._data["members"].items():
            if secrets.compare_digest(digest, value.get("token_hash", "")):
                found = member
        return found

    def can_skip(self, day: str) -> bool:
        parsed = planner.parse_day(day)
        return parsed is not None and parsed in planner.horizon(dt_util.now().date(), self.office_days)

    def set_skip(self, member: str, day: str, skip: bool) -> None:
        planner.set_skip(self._data["skips"].setdefault(member, {}), day, skip, time.time())
        self._promote()
        self._changed()

    def add_member(self, name: str) -> str:
        """A new token for the colleague of this name; a name that exists keeps its skip days."""
        token = secrets.token_urlsafe(32)
        member = planner.member_id(name)
        self._data["members"][member] = {"name": name.strip(), "token_hash": _hash(token)}
        self._save()
        self._changed()
        return token

    def remove_member(self, member: str) -> None:
        if member == self.me:
            return
        self._data["members"].pop(member, None)
        self._data["skips"].pop(member, None)
        self._save()
        self._changed()

    @callback
    def _promote(self, _now=None) -> None:
        self.async_stop()
        today = dt_util.now().date()
        published = False
        for records in self._data["skips"].values():
            planner.prune(records, today)
            published |= planner.promote(records, time.time())
        self._save()
        waiting = [t for r in self._data["skips"].values() if (t := planner.next_promotion(r)) is not None]
        if waiting:
            self._timer = async_call_later(self.hass, max(0, min(waiting) - time.time()) + 0.5, self._promote)
        if published:
            self._changed()

    def _save(self) -> None:
        self._store.async_delay_save(lambda: self._data, 1)

    def _changed(self) -> None:
        for listener in list(self._listeners):
            listener()
