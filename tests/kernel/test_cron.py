"""Tests for CronExpression parser."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from app.kernel.scheduler import CronExpression, CronParseError


class TestCronExpressionParse:
    def test_every_minute(self):
        c = CronExpression("* * * * *")
        assert c.matches(time.time())

    def test_specific_minute(self):
        dt = datetime.now(timezone.utc)
        expr = f"{dt.minute} * * * *"
        c = CronExpression(expr)
        assert c.matches(dt.timestamp())

    def test_wrong_minute_does_not_match(self):
        dt = datetime.now(timezone.utc)
        wrong = (dt.minute + 1) % 60
        expr = f"{wrong} * * * *"
        c = CronExpression(expr)
        assert not c.matches(dt.timestamp())

    def test_specific_hour(self):
        dt = datetime.now(timezone.utc)
        expr = f"* {dt.hour} * * *"
        c = CronExpression(expr)
        assert c.matches(dt.timestamp())

    def test_range_syntax(self):
        c = CronExpression("0 9-17 * * *")
        dt = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
        assert c.matches(dt.timestamp())

    def test_list_syntax(self):
        c = CronExpression("0,30 * * * *")
        dt = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
        assert c.matches(dt.timestamp())
        dt2 = datetime(2026, 1, 15, 12, 30, tzinfo=timezone.utc)
        assert c.matches(dt2.timestamp())

    def test_step_syntax(self):
        c = CronExpression("*/15 * * * *")
        dt = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
        assert c.matches(dt.timestamp())
        dt2 = datetime(2026, 1, 15, 12, 15, tzinfo=timezone.utc)
        assert c.matches(dt2.timestamp())
        dt3 = datetime(2026, 1, 15, 12, 45, tzinfo=timezone.utc)
        assert c.matches(dt3.timestamp())
        dt4 = datetime(2026, 1, 15, 12, 10, tzinfo=timezone.utc)
        assert not c.matches(dt4.timestamp())

    def test_step_with_range(self):
        c = CronExpression("0 1-10/3 * * *")
        dt = datetime(2026, 1, 15, 1, 0, tzinfo=timezone.utc)
        assert c.matches(dt.timestamp())
        dt2 = datetime(2026, 1, 15, 4, 0, tzinfo=timezone.utc)
        assert c.matches(dt2.timestamp())
        dt3 = datetime(2026, 1, 15, 2, 0, tzinfo=timezone.utc)
        assert not c.matches(dt3.timestamp())

    def test_named_month(self):
        c = CronExpression("0 0 1 JAN *")
        dt = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        assert c.matches(dt.timestamp())
        dt2 = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
        assert not c.matches(dt2.timestamp())

    def test_named_weekday(self):
        # 2026-01-15 is Thursday
        c = CronExpression("0 0 * * THU")
        dt = datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
        assert c.matches(dt.timestamp())
        dt2 = datetime(2026, 1, 17, 0, 0, tzinfo=timezone.utc)
        assert not c.matches(dt2.timestamp())

    def test_invalid_field_count_raises(self):
        with pytest.raises(CronParseError):
            CronExpression("* * * *")

    def test_too_many_fields_raises(self):
        with pytest.raises(CronParseError):
            CronExpression("* * * * * *")

    def test_out_of_range_value_raises(self):
        with pytest.raises(CronParseError):
            CronExpression("60 * * * *")

    def test_negative_value_raises(self):
        with pytest.raises(CronParseError):
            CronExpression("-1 * * * *")

    def test_string_with_extra_spaces(self):
        c = CronExpression("  0  *   *  *  *  ")
        assert c._minute.values == {0}

    def test_next_after_returns_future_timestamp(self):
        c = CronExpression("0 3 * * *")
        now = time.time()
        next_time = c.next_after(now)
        assert next_time is not None
        assert next_time > now

    def test_next_after_every_minute(self):
        c = CronExpression("* * * * *")
        now = time.time()
        next_time = c.next_after(now)
        assert next_time is not None
        assert next_time > now

    def test_next_after_never_matches(self):
        c = CronExpression("0 0 30 FEB *")
        now = time.time()
        next_time = c.next_after(now)
        assert next_time is None

    def test_specific_day_of_week(self):
        # 2026-01-15 is Thursday (Python=3, cron=4)
        c = CronExpression("0 0 * * 4")
        dt = datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
        assert c.matches(dt.timestamp())

    def test_multiple_months(self):
        c = CronExpression("0 0 1 1,6,12 *")
        dt_jan = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        dt_jun = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
        dt_dec = datetime(2026, 12, 1, 0, 0, tzinfo=timezone.utc)
        dt_mar = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)
        assert c.matches(dt_jan.timestamp())
        assert c.matches(dt_jun.timestamp())
        assert c.matches(dt_dec.timestamp())
        assert not c.matches(dt_mar.timestamp())
