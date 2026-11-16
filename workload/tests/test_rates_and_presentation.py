import copy
import unittest
from datetime import date
from pathlib import Path

from workload.calculation import compute_days
from workload.presentation import build_week, build_year, fmt_date_range, fmt_num, nice_axis
from workload.ratesconfig import RatesError, load_rates, parse_rates

from .helpers import EXAMPLE_SERIES, SPEC_RATES, TEST_RATES_PATH, spec_rates

PROJECT_DIR = Path(__file__).resolve().parents[2]


class RatesConfigTests(unittest.TestCase):
    def test_live_rates_file_is_valid(self):
        """rates.toml can hold any values, as long as the file is valid."""
        load_rates(PROJECT_DIR / "rates.toml")

    def test_test_rates_file_matches_spec(self):
        self.assertEqual(load_rates(TEST_RATES_PATH), spec_rates())

    def test_schedule_must_sum_to_one(self):
        data = copy.deepcopy(SPEC_RATES)
        data["collection"]["schedule"] = [0.6, 0.3]
        with self.assertRaisesRegex(RatesError, "add up to 1.0"):
            parse_rates(data)

    def test_missing_value(self):
        data = copy.deepcopy(SPEC_RATES)
        del data["handling"]["booking"]
        with self.assertRaisesRegex(RatesError, "handling.booking"):
            parse_rates(data)

    def test_unknown_key_is_reported(self):
        data = copy.deepcopy(SPEC_RATES)
        data["handling"]["bookng"] = 0.2
        with self.assertRaisesRegex(RatesError, "bookng"):
            parse_rates(data)

    def test_every_type_needs_a_pallet_figure(self):
        data = copy.deepcopy(SPEC_RATES)
        del data["pallets_per_series"]
        with self.assertRaisesRegex(RatesError, "no pallet figure for cushions"):
            parse_rates(data)

    def test_old_single_pallet_setting_gives_clear_error(self):
        data = copy.deepcopy(SPEC_RATES)
        data["storage"]["pallets_per_100"] = 30
        with self.assertRaisesRegex(RatesError, r"replaced by the \[pallets_per_100\] section"):
            parse_rates(data)

    def test_one_piece_handling_rejects_unknown_task(self):
        data = copy.deepcopy(SPEC_RATES)
        data["one_piece_handling"]["cushions"].append("picking")
        with self.assertRaisesRegex(RatesError, "unknown task"):
            parse_rates(data)

    def test_task_override_rejects_unknown_task(self):
        data = copy.deepcopy(SPEC_RATES)
        data["task_overrides"]["picking"] = {"mixed": {"per_100": 1}}
        with self.assertRaisesRegex(RatesError, "picking"):
            parse_rates(data)

    def test_task_override_needs_a_value(self):
        data = copy.deepcopy(SPEC_RATES)
        data["task_overrides"]["booking"]["dsv"] = {}
        with self.assertRaisesRegex(RatesError, "task_overrides.booking.dsv"):
            parse_rates(data)

    def test_bad_closed_day(self):
        with self.assertRaises(RatesError):
            spec_rates(extra_closed_days=["24-12"])


class FormattingTests(unittest.TestCase):
    def test_danish_numbers(self):
        self.assertEqual(fmt_num(1234.56), "1.234,6")
        self.assertEqual(fmt_num(69), "69,0")

    def test_date_ranges(self):
        self.assertEqual(fmt_date_range(date(2026, 11, 9), date(2026, 11, 13)), "9.–13. november 2026")
        self.assertEqual(fmt_date_range(date(2026, 12, 28), date(2027, 1, 1)),
                         "28. december 2026 – 1. januar 2027")

    def test_nice_axis(self):
        self.assertEqual(nice_axis(69), (80, [0, 20, 40, 60, 80]))
        self.assertEqual(nice_axis(0)[0], 10)
        top, ticks = nice_axis(3.2)
        self.assertGreaterEqual(top, 3.2)


class BuildWeekTests(unittest.TestCase):
    def test_week_context(self):
        rates = spec_rates()
        dates = [date(2026, 12, d) for d in range(21, 26)]  # Friday 25th is Juledag
        results = compute_days(dates, {date(2026, 12, 21): EXAMPLE_SERIES}, rates)
        ctx = build_week(dates, results)
        monday = ctx["days"][0]
        self.assertEqual(monday["weekday"], "Mandag")
        self.assertEqual(monday["total"], "88,3")
        self.assertEqual(monday["status_label"], "Stram")
        self.assertEqual(monday["segments"][0]["key"], "picking")
        self.assertEqual(ctx["days"][4]["closed"], "Juledag")
        self.assertTrue(ctx["has_data"])
        self.assertEqual(ctx["week_items"], "1.400")
        # Monday 88,343 + Tuesday 8,4 + Wednesday 4,2 + Thursday 1,4
        self.assertEqual(ctx["week_hours"], "102,3")
        self.assertEqual(monday["employees"], 12)
        self.assertEqual(monday["employees_exact"], "11,8")
        self.assertEqual(monday["pallets"], "280")
        self.assertEqual(monday["occupancy"], "70")
        self.assertNotIn("pallets_awaiting", monday)
        self.assertEqual(monday["pallets_new"], "378")
        self.assertTrue(monday["has_pallets_new"])
        self.assertFalse(ctx["days"][1]["has_pallets_new"])
        self.assertEqual(monday["surcharge_pct"], "15")
        self.assertEqual(monday["surcharge_hours"], "11,5")
        # 102,343 h / 7,5 h = 13,65 employee-days over 4 open days (Friday is Juledag)
        self.assertEqual(ctx["week_employees_avg"], "3,4")
        self.assertEqual(ctx["week_employees_max"], 12)
        detail_labels = [row["label"] for row in ctx["details"]]
        self.assertIn("Lagerudnyttelse", detail_labels)
        self.assertNotIn("Stk. udleveret", detail_labels)
        self.assertNotIn("Paller på lager", detail_labels)
        labels = [s["label"] for s in monday["segments"]]
        self.assertIn("Strækfilm", labels)
        self.assertNotIn("Pakning", labels)
        self.assertNotIn("Indpakning", labels)

    def test_year_has_twelve_months(self):
        rates = spec_rates()
        dates = [date(2026, 1, 1)]
        months = build_year(2026, compute_days(dates, {}, rates), today=date(2026, 11, 11))
        self.assertEqual(len(months), 12)
        november_weeks = [w["week"] for w in months[10]["weeks"]]
        self.assertIn(46, november_weeks)


if __name__ == "__main__":
    unittest.main()
