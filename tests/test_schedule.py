from datetime import datetime, time

from schedule import is_active

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"]


def at(day: str, hhmm: str) -> datetime:
    # 2026-10-05 is a Monday
    d = {"mon": 5, "tue": 6, "wed": 7, "thu": 8, "fri": 9, "sat": 10, "sun": 11}[day]
    return datetime.fromisoformat(f"2026-10-{d:02d}T{hhmm}:00+02:00")


def test_inside_and_outside_a_morning_window():
    start, end = time(6), time(10)
    assert is_active(at("mon", "06:00"), start, end, WEEKDAYS)
    assert is_active(at("mon", "09:59"), start, end, WEEKDAYS)
    assert not is_active(at("mon", "10:00"), start, end, WEEKDAYS)
    assert not is_active(at("mon", "05:59"), start, end, WEEKDAYS)


def test_only_on_selected_days():
    assert not is_active(at("sat", "07:00"), time(6), time(10), WEEKDAYS)
    assert is_active(at("sat", "07:00"), time(6), time(10), ["sat"])


def test_same_start_and_end_means_all_day():
    assert is_active(at("wed", "03:00"), time(0), time(0), WEEKDAYS)
    assert not is_active(at("sun", "03:00"), time(0), time(0), WEEKDAYS)


def test_window_past_midnight_belongs_to_the_day_it_started():
    start, end = time(22), time(1)
    assert is_active(at("fri", "23:30"), start, end, ["fri"])
    assert is_active(at("sat", "00:30"), start, end, ["fri"])  # Friday's window
    assert not is_active(at("sat", "00:30"), start, end, ["sat"])
    assert not is_active(at("sat", "12:00"), start, end, ["fri", "sat"])
