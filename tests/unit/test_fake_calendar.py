"""FakeCalendarService is deterministic and matches the surface the tools call."""

from evals.fakes import FakeCalendarService


def test_create_event_returns_incrementing_synthetic_ids():
    fake = FakeCalendarService()
    a = fake.create_event(summary="s", start=None, end=None)
    b = fake.create_event(summary="s", start=None, end=None)
    assert a["id"] != b["id"]
    assert a["id"].startswith("fake-")


def test_update_and_cancel_are_noops_returning_expected_shapes():
    fake = FakeCalendarService()
    assert fake.update_event("fake-1", start=None, end=None)["id"] == "fake-1"
    assert fake.cancel_event("fake-1") is None
    assert fake.list_events(None, None) == []


def test_build_weekly_rrule_delegates():
    rule = FakeCalendarService.build_weekly_rrule(["TU"], None)
    assert rule.startswith("RRULE:FREQ=WEEKLY") and "BYDAY=TU" in rule
