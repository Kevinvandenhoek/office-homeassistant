"""The skip days without Home Assistant: which days count, the grace minute, what changed and what to say.

Pure, so it is tested in tests/test_planner.py without Home Assistant.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import re

# A change reaches the others only after this many seconds, so a tap by mistake can be undone.
GRACE = 60
DEFAULT_OFFICE_DAYS = [0, 1, 2, 3]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NAME_RE = re.compile(r"[^a-z0-9]+")


def member_id(name: str) -> str:
    """The id of a member from their name: "Mitchell" is mitchell."""
    return NAME_RE.sub("_", name.strip().lower()).strip("_")


def horizon(today: date, office_days: list[int]) -> list[date]:
    """The office days from today up to and including Sunday of next week."""
    end = today + timedelta(days=13 - today.weekday())
    days = []
    day = today
    while day <= end:
        if day.weekday() in office_days:
            days.append(day)
        day += timedelta(days=1)
    return days


def parse_day(text: str) -> date | None:
    if not isinstance(text, str) or not DATE_RE.match(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


# A record per member and date: {"skip": what the member wants, "since": when that was set (epoch seconds),
# "published": what the others see}.


def set_skip(records: dict[str, dict], day: str, skip: bool, now: float) -> None:
    """The member wants `skip` on `day`; the others see it after the grace minute."""
    record = records.get(day)
    if record is None:
        if skip:
            records[day] = {"skip": True, "since": now, "published": False}
        return
    if record["skip"] != skip:
        record["skip"] = skip
        record["since"] = now


def promote(records: dict[str, dict], now: float) -> bool:
    """Publish what has held for the grace minute; True when the others see something new."""
    changed = False
    for day in list(records):
        record = records[day]
        if record["skip"] != record["published"] and now - record["since"] >= GRACE:
            record["published"] = record["skip"]
            changed = True
        if not record["skip"] and not record["published"]:
            del records[day]
    return changed


def next_promotion(records: dict[str, dict]) -> float | None:
    """When the next waiting change is published, in epoch seconds."""
    waiting = [r["since"] + GRACE for r in records.values() if r["skip"] != r["published"]]
    return min(waiting) if waiting else None


def prune(records: dict[str, dict], today: date) -> None:
    for day in list(records):
        if day < today.isoformat():
            del records[day]


def view(members: dict[str, str], skips: dict[str, dict[str, dict]], office_days: list[int], me: str,
         today: date) -> dict:
    """What a member sees: the API answer of the host, and the data of the entities."""
    days = [d.isoformat() for d in horizon(today, office_days)]
    published = {m: sorted(d for d, r in skips.get(m, {}).items() if r["published"] and d in days) for m in members}
    mine = skips.get(me, {})
    return {
        "version": 1,
        "me": me,
        "members": members,
        "office_days": office_days,
        "today": today.isoformat(),
        "days": days,
        "skips": published,
        "mine": sorted(d for d, r in mine.items() if r["skip"] and d in days),
        "pending": {d: r["since"] + GRACE for d, r in mine.items() if r["skip"] != r["published"] and d in days},
    }


def colleagues(data: dict) -> dict[str, list[str]]:
    """The published skip days of everyone but me."""
    return {m: list(days) for m, days in data.get("skips", {}).items() if m != data.get("me")}


@dataclass(frozen=True)
class Change:
    member: str
    day: str
    skip: bool


def changes(seen: dict[str, list[str]], now: dict[str, list[str]], today: date) -> list[Change]:
    """What changed at the colleagues since the last look, today and later."""
    out = []
    for member in sorted(set(seen) | set(now)):
        before, after = set(seen.get(member, [])), set(now.get(member, []))
        for day in sorted(after - before):
            out.append(Change(member, day, True))
        for day in sorted(before - after):
            if day >= today.isoformat():
                out.append(Change(member, day, False))
    return out


def day_name(day: str, today: date) -> str:
    """"today", "tomorrow", "Thursday" in this week, else "Thursday 29 October"."""
    d = date.fromisoformat(day)
    delta = (d - today).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    if d.isocalendar()[:2] == today.isocalendar()[:2]:
        return WEEKDAYS[d.weekday()]
    return f"{WEEKDAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"


def message(change: Change, name: str, today: date) -> str:
    when = day_name(change.day, today)
    if change.skip:
        return f"{name} skips {when}."
    on = when if when in ("today", "tomorrow") else f"on {when}"
    return f"{name} comes to the office {on} after all."


def should_notify(change: Change, today: date, now: time, until: time) -> bool:
    """A change about today only before `until`, a later day always, a past day never."""
    if change.day < today.isoformat():
        return False
    return change.day != today.isoformat() or now < until


def skipping_today(data: dict, today: date) -> list[str]:
    """The names of the colleagues who skip today."""
    names = data.get("members", {})
    return [names.get(m, m) for m, days in colleagues(data).items() if today.isoformat() in days]


def morning_message(names: list[str]) -> str:
    if len(names) == 1:
        return f"{names[0]} skips today."
    return f"{', '.join(names[:-1])} and {names[-1]} skip today."


def due(at: time, now: datetime, last: str | None) -> bool:
    """The morning reminder is due: its time has come today, less than half an hour ago, and it has not gone
    today; the half hour lets a restart at that moment still send it, but not one in the afternoon."""
    start = now.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    return last != now.date().isoformat() and timedelta(0) <= now - start < timedelta(minutes=30)
