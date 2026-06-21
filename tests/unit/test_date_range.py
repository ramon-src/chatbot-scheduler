from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.utils.date_range import calculate_date_range

TZ = ZoneInfo("America/Sao_Paulo")
# 2026-06-21 is a Sunday, 14:30 local
NOW = datetime(2026, 6, 21, 14, 30, tzinfo=TZ)


def test_today():
    start, end = calculate_date_range("today", NOW)
    assert start == datetime(2026, 6, 21, 0, 0, tzinfo=TZ)
    assert end == datetime(2026, 6, 22, 0, 0, tzinfo=TZ)


def test_tomorrow():
    start, end = calculate_date_range("tomorrow", NOW)
    assert start == datetime(2026, 6, 22, 0, 0, tzinfo=TZ)
    assert end == datetime(2026, 6, 23, 0, 0, tzinfo=TZ)


def test_this_week_starts_sunday():
    # NOW is Sunday -> week is 21st (Sun) through 28th (next Sun, exclusive)
    start, end = calculate_date_range("this_week", NOW)
    assert start == datetime(2026, 6, 21, 0, 0, tzinfo=TZ)
    assert end == datetime(2026, 6, 28, 0, 0, tzinfo=TZ)


def test_this_week_midweek_rolls_back_to_sunday():
    wed = datetime(2026, 6, 24, 9, 0, tzinfo=TZ)  # Wednesday
    start, end = calculate_date_range("this_week", wed)
    assert start == datetime(2026, 6, 21, 0, 0, tzinfo=TZ)
    assert end == datetime(2026, 6, 28, 0, 0, tzinfo=TZ)


def test_next_week():
    start, end = calculate_date_range("next_week", NOW)
    assert start == datetime(2026, 6, 28, 0, 0, tzinfo=TZ)
    assert end == datetime(2026, 7, 5, 0, 0, tzinfo=TZ)


def test_this_month():
    start, end = calculate_date_range("this_month", NOW)
    assert start == datetime(2026, 6, 1, 0, 0, tzinfo=TZ)
    assert end == datetime(2026, 7, 1, 0, 0, tzinfo=TZ)


def test_all_future_capped_one_year():
    start, end = calculate_date_range("all_future", NOW)
    assert start == datetime(2026, 6, 21, 0, 0, tzinfo=TZ)
    assert (end - start).days == 366


def test_accent_and_case_insensitive_aliases():
    assert calculate_date_range("HOJE", NOW) == calculate_date_range("today", NOW)
    assert calculate_date_range("esta semana", NOW) == calculate_date_range("this_week", NOW)


def test_unknown_period_raises():
    with pytest.raises(ValueError):
        calculate_date_range("yesterday", NOW)
