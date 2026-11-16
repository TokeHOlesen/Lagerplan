import unittest
from datetime import date

from workload.calendar_dk import WorkCalendar, danish_public_holidays, easter_sunday, week_dates, weeks_in_year


class EasterTests(unittest.TestCase):
    def test_known_easter_dates(self):
        self.assertEqual(easter_sunday(2024), date(2024, 3, 31))
        self.assertEqual(easter_sunday(2025), date(2025, 4, 20))
        self.assertEqual(easter_sunday(2026), date(2026, 4, 5))
        self.assertEqual(easter_sunday(2027), date(2027, 3, 28))


class HolidayTests(unittest.TestCase):
    def test_2026_holidays(self):
        h = danish_public_holidays(2026)
        self.assertEqual(h[date(2026, 1, 1)], "Nytårsdag")
        self.assertEqual(h[date(2026, 4, 2)], "Skærtorsdag")
        self.assertEqual(h[date(2026, 4, 3)], "Langfredag")
        self.assertEqual(h[date(2026, 4, 6)], "2. påskedag")
        self.assertEqual(h[date(2026, 5, 14)], "Kristi himmelfartsdag")
        self.assertEqual(h[date(2026, 5, 25)], "2. pinsedag")
        self.assertEqual(h[date(2026, 12, 25)], "Juledag")
        self.assertEqual(h[date(2026, 12, 26)], "2. juledag")

    def test_store_bededag_only_until_2023(self):
        self.assertEqual(danish_public_holidays(2023)[date(2023, 5, 5)], "Store bededag")
        self.assertNotIn("Store bededag", danish_public_holidays(2024).values())

    def test_grundlovsdag_not_closed_by_default(self):
        self.assertTrue(WorkCalendar().is_workday(date(2026, 6, 5)))


class WorkCalendarTests(unittest.TestCase):
    def test_weekend_and_holiday_closed(self):
        cal = WorkCalendar()
        self.assertEqual(cal.closed_reason(date(2026, 11, 14)), "Weekend")
        self.assertEqual(cal.closed_reason(date(2026, 12, 25)), "Juledag")
        self.assertIsNone(cal.closed_reason(date(2026, 11, 11)))

    def test_extra_closed_days(self):
        cal = WorkCalendar(extra_yearly=frozenset({(12, 24)}), extra_dates=frozenset({date(2026, 12, 28)}))
        self.assertEqual(cal.closed_reason(date(2026, 12, 24)), "Juleaftensdag")
        self.assertEqual(cal.closed_reason(date(2026, 12, 28)), "Lukket")

    def test_previous_workdays_skip_weekend_and_holidays(self):
        cal = WorkCalendar()
        # Tuesday 7 April 2026: Monday 6 is 2. påskedag, Thu 2 and Fri 3 are holidays.
        self.assertEqual(cal.previous_workdays(date(2026, 4, 7), 3),
                         [date(2026, 4, 1), date(2026, 3, 31), date(2026, 3, 30)])


class WeekTests(unittest.TestCase):
    def test_week_dates(self):
        self.assertEqual(week_dates(2026, 46), [date(2026, 11, d) for d in range(9, 14)])

    def test_week_53(self):
        self.assertEqual(weeks_in_year(2026), 53)
        self.assertEqual(week_dates(2026, 53)[-1], date(2027, 1, 1))
        with self.assertRaises(ValueError):
            week_dates(2025, 53)


if __name__ == "__main__":
    unittest.main()
