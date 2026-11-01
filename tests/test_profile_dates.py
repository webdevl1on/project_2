from datetime import date,datetime,UTC
from app.utils.date_utils import format_calendar_date,format_system_timestamp


def test_calendar_presentation_is_dmy_and_does_not_invent_partial_values():
    assert format_calendar_date(date(2026,10,31))=='31.10.2026'
    assert format_calendar_date('2026-11-05')=='05.11.2026'
    assert format_calendar_date('15._.1993')=='15._.1993'
    assert format_calendar_date(None)=='—'


def test_system_timestamp_keeps_exact_utc_policy_and_precision():
    stamp=datetime(2026,10,31,23,12,13,123456,tzinfo=UTC)
    assert format_calendar_date(stamp)==format_system_timestamp(stamp)=='31.10.2026 23:12:13.123456 UTC'
