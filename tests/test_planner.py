"""The skip day logic, without Home Assistant."""

from datetime import date, datetime, time, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "office"))

import planner  # noqa: E402

THU = date(2026, 10, 22)


def test_horizon_runs_to_sunday_next_week_on_office_days():
    days = planner.horizon(THU, [0, 1, 2, 3])
    assert days[0] == THU
    assert days[-1] == date(2026, 10, 29)
    assert [d.isoformat() for d in days] == ["2026-10-22", "2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29"]


def test_horizon_on_a_sunday_is_next_week_only():
    days = planner.horizon(date(2026, 10, 25), [0, 1, 2, 3])
    assert [d.isoformat() for d in days] == ["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29"]


def test_grace_minute_publishes_after_sixty_seconds():
    records = {}
    planner.set_skip(records, "2026-10-26", True, 1000)
    assert not planner.promote(records, 1059)
    assert records["2026-10-26"]["published"] is False
    assert planner.next_promotion(records) == 1060
    assert planner.promote(records, 1060)
    assert records["2026-10-26"]["published"] is True
    assert planner.next_promotion(records) is None


def test_undo_within_the_grace_minute_sends_nothing():
    records = {}
    planner.set_skip(records, "2026-10-26", True, 1000)
    planner.set_skip(records, "2026-10-26", False, 1030)
    assert not planner.promote(records, 2000)
    assert records == {}


def test_back_and_forth_after_publish_sends_nothing():
    records = {}
    planner.set_skip(records, "2026-10-26", True, 1000)
    planner.promote(records, 1060)
    planner.set_skip(records, "2026-10-26", False, 2000)
    planner.set_skip(records, "2026-10-26", True, 2020)
    assert not planner.promote(records, 3000)
    assert records["2026-10-26"]["published"] is True


def test_turning_off_is_published_and_the_record_goes():
    records = {}
    planner.set_skip(records, "2026-10-26", True, 1000)
    planner.promote(records, 1060)
    planner.set_skip(records, "2026-10-26", False, 2000)
    assert planner.promote(records, 2060)
    assert records == {}


def test_view_shows_published_to_others_and_pending_to_me():
    skips = {
        "kevin": {"2026-10-26": {"skip": True, "since": 1000, "published": False}},
        "mitchell": {"2026-10-22": {"skip": True, "since": 0, "published": True},
                     "2026-10-23": {"skip": True, "since": 0, "published": True}},
    }
    members = {"kevin": "Kevin", "mitchell": "Mitchell"}
    v = planner.view(members, skips, [0, 1, 2, 3], "kevin", THU)
    # Friday is no office day, so it is not shown.
    assert v["skips"] == {"kevin": [], "mitchell": ["2026-10-22"]}
    assert v["mine"] == ["2026-10-26"]
    assert v["pending"] == {"2026-10-26": 1060}
    assert planner.skipping_today(v, THU) == ["Mitchell"]


def test_changes_and_messages():
    seen = {"mitchell": ["2026-10-22", "2026-10-28"]}
    now = {"mitchell": ["2026-10-29"], "kevin": ["2026-10-26"]}
    found = planner.changes(seen, now, THU)
    assert found == [
        planner.Change("kevin", "2026-10-26", True),
        planner.Change("mitchell", "2026-10-29", True),
        planner.Change("mitchell", "2026-10-22", False),
        planner.Change("mitchell", "2026-10-28", False),
    ]
    assert planner.message(found[1], "Mitchell", THU) == "Mitchell skips Thursday 29 October."
    assert planner.message(found[2], "Mitchell", THU) == "Mitchell comes to the office today after all."
    assert planner.message(found[3], "Mitchell", THU) == "Mitchell comes to the office on Wednesday 28 October after all."
    assert planner.message(planner.Change("m", "2026-10-23", True), "Mitchell", THU) == "Mitchell skips tomorrow."
    assert planner.message(planner.Change("m", "2026-10-26", True), "Mitchell", date(2026, 10, 25)) == "Mitchell skips tomorrow."
    assert planner.message(planner.Change("m", "2026-10-28", True), "Mitchell", date(2026, 10, 26)) == "Mitchell skips Wednesday."


def test_a_day_that_passed_is_no_change():
    assert planner.changes({"mitchell": ["2026-10-21"]}, {"mitchell": []}, THU) == []


def test_today_only_until_the_cut_off():
    today = planner.Change("mitchell", "2026-10-22", True)
    later = planner.Change("mitchell", "2026-10-26", True)
    noon = time(12, 0)
    assert planner.should_notify(today, THU, time(9, 0), noon)
    assert not planner.should_notify(today, THU, time(12, 30), noon)
    assert planner.should_notify(later, THU, time(18, 0), noon)


def test_morning_reminder_is_due_once_within_half_an_hour():
    at = time(7, 30)
    tz = timezone.utc
    assert not planner.due(at, datetime(2026, 10, 22, 7, 29, tzinfo=tz), None)
    assert planner.due(at, datetime(2026, 10, 22, 7, 30, tzinfo=tz), None)
    assert planner.due(at, datetime(2026, 10, 22, 7, 55, tzinfo=tz), "2026-10-21")
    assert not planner.due(at, datetime(2026, 10, 22, 7, 31, tzinfo=tz), "2026-10-22")
    assert not planner.due(at, datetime(2026, 10, 22, 8, 1, tzinfo=tz), None)
    assert planner.morning_message(["Mitchell"]) == "Mitchell skips today."
    assert planner.morning_message(["Mitchell", "Sam", "Kevin"]) == "Mitchell, Sam and Kevin skip today."


def test_member_id():
    assert planner.member_id(" Mitchell ") == "mitchell"
    assert planner.member_id("Anne-Marie de Vries") == "anne_marie_de_vries"
