import copy
import unittest
from datetime import date

from workload.calculation import GOOD, OVER, TIGHT, VERY_TIGHT, compute_days, employees_needed, lookback_start
from workload.ratesconfig import parse_rates

from .helpers import EXAMPLE_SERIES, SPEC_RATES, spec_rates

MON, TUE, WED, THU, FRI = (date(2026, 11, d) for d in range(9, 14))
WEEK = [MON, TUE, WED, THU, FRI]


class SingleDayTests(unittest.TestCase):
    def setUp(self):
        self.rates = spec_rates()

    def test_worked_example_monday(self):
        """1,000 pcs Mixed + 400 pcs Large same: 76.82 h, 280 pallets (70 %), tight, +15 % = 88.343 h."""
        r = compute_days([MON], {MON: EXAMPLE_SERIES}, self.rates)[MON]
        self.assertAlmostEqual(r.hours["picking"], 34)
        self.assertAlmostEqual(r.hours["forklift"], 14)
        self.assertAlmostEqual(r.hours["wrapping"], 21)
        self.assertAlmostEqual(r.hours["booking"], 3.5 + 0.12)
        self.assertAlmostEqual(r.hours["labeling"], 4.2)
        self.assertAlmostEqual(r.hours["collection"], 0)
        self.assertAlmostEqual(r.subtotal, 76.82)
        self.assertAlmostEqual(r.pallets, 280)
        self.assertEqual(r.storage_status, TIGHT)
        self.assertAlmostEqual(r.hours["surcharge"], 76.82 * 0.15)
        self.assertAlmostEqual(r.total, 76.82 * 1.15)

    def test_mixed_alone_is_good_storage(self):
        """1,000 pcs Mixed = 220 pallets = 55 % of 400: no surcharge."""
        r = compute_days([MON], {MON: [("mixed", 1000)]}, self.rates)[MON]
        self.assertAlmostEqual(r.pallets, 220)
        self.assertEqual(r.storage_status, GOOD)
        self.assertAlmostEqual(r.total, 30 + 10 + 15 + 3.5 + 3)

    def test_pallets_made_ready_today(self):
        results = compute_days(WEEK, {MON: EXAMPLE_SERIES, TUE: [("cushions", 300), ("cushions", 50)]}, self.rates)
        self.assertAlmostEqual(results[MON].pallets_new, 378)  # 1,400 pcs x 27 / 100, any type
        self.assertAlmostEqual(results[MON].pallets, 280)      # storage still uses per-type figures
        self.assertAlmostEqual(results[TUE].pallets_new, 2)    # 1 per cushion series
        self.assertAlmostEqual(results[WED].pallets_new, 0)    # collection days add none

    def test_pallet_estimate_mixed_types(self):
        r = compute_days([MON], {MON: [("dsv", 200), ("large_same", 100), ("cushions", 400)]}, self.rates)[MON]
        self.assertAlmostEqual(r.pallets_new, 300 * 27 / 100 + 1)

    def test_pallet_estimate_defaults(self):
        data = {k: v for k, v in SPEC_RATES.items() if k != "pallet_estimate"}
        rates = parse_rates(data)
        self.assertEqual((rates.estimate_per_100, dict(rates.estimate_per_series)), (27.0, {"cushions": 1.0}))

    def test_pallets_per_type(self):
        for series_type, items, pallets in [("mixed", 100, 22), ("dsv", 100, 20), ("large_mixed", 100, 18),
                                            ("large_same", 100, 15), ("large_same", 250, 37.5)]:
            with self.subTest(series_type=series_type, items=items):
                r = compute_days([MON], {MON: [(series_type, items)]}, self.rates)[MON]
                self.assertAlmostEqual(r.pallets, pallets)

    def test_picking_rates_per_series_type(self):
        picks = {MON: [("mixed", 100), ("dsv", 100), ("large_mixed", 200), ("large_same", 100)]}
        r = compute_days([MON], picks, self.rates)[MON]
        self.assertAlmostEqual(r.hours["picking"], 3 + 2 + 3 + 1)
        self.assertEqual(r.items_picked, 500)
        self.assertAlmostEqual(r.hours["forklift"], 5)
        self.assertAlmostEqual(r.hours["wrapping"], 7.5)
        self.assertAlmostEqual(r.hours["booking"], 0.35 + 3 * 0.12)  # mixed per pcs, others per series
        self.assertAlmostEqual(r.hours["labeling"], 1.5)

    def test_booking_by_type(self):
        for series_type, items, hours in [("mixed", 100, 0.35), ("mixed", 2000, 7.0),
                                          ("dsv", 100, 0.12), ("dsv", 5000, 0.12),
                                          ("large_mixed", 800, 0.12), ("large_same", 1, 0.12),
                                          ("cushions", 300, 0.12)]:
            with self.subTest(series_type=series_type, items=items):
                r = compute_days([MON], {MON: [(series_type, items)]}, self.rates)[MON]
                self.assertAlmostEqual(r.hours["booking"], hours)
        two = compute_days([MON], {MON: [("dsv", 100), ("dsv", 900)]}, self.rates)[MON]
        self.assertAlmostEqual(two.hours["booking"], 0.24)

    def test_without_task_overrides_section_defaults_apply(self):
        data = {k: v for k, v in SPEC_RATES.items() if k != "task_overrides"}
        self.assertEqual(parse_rates(data).task_overrides, spec_rates().task_overrides)

    def test_empty_day(self):
        r = compute_days([MON], {}, self.rates)[MON]
        self.assertEqual(r.total, 0)
        self.assertEqual(r.storage_status, GOOD)


class CushionTests(unittest.TestCase):
    def setUp(self):
        self.rates = spec_rates()

    def test_cushion_hours(self):
        """500 pcs Hynder: picking per piece; forklift, wrapping, labeling as 1 piece; booking 0.12 h."""
        r = compute_days([MON], {MON: [("cushions", 500)]}, self.rates)[MON]
        self.assertEqual(r.items_picked, 500)
        self.assertAlmostEqual(r.hours["picking"], 6)        # 500 x 1.2 / 100
        self.assertAlmostEqual(r.hours["labeling"], 0.003)   # 1 x 0.3 / 100
        self.assertAlmostEqual(r.hours["forklift"], 0.01)    # 1 x 1.0 / 100
        self.assertAlmostEqual(r.hours["wrapping"], 0.015)   # 1 x 1.5 / 100
        self.assertAlmostEqual(r.hours["booking"], 0.12)     # per series
        self.assertAlmostEqual(r.subtotal, 6 + 0.003 + 0.01 + 0.015 + 0.12)

    def test_cushions_mixed_with_other_series(self):
        picks = {MON: [("mixed", 100), ("cushions", 100), ("cushions", 300)]}
        r = compute_days([MON], picks, self.rates)[MON]
        self.assertEqual(r.items_picked, 500)
        self.assertAlmostEqual(r.hours["picking"], 3 + 1.2 + 3.6)
        self.assertAlmostEqual(r.hours["forklift"], (100 + 1 + 1) * 1.0 / 100)
        self.assertAlmostEqual(r.hours["labeling"], (100 + 1 + 1) * 0.3 / 100)
        self.assertAlmostEqual(r.pallets, 22 + 1 + 1)

    def test_cushion_collection_counts_one_piece_per_series(self):
        results = compute_days(WEEK, {MON: [("cushions", 300), ("cushions", 200)]}, self.rates)
        # 2 series = 2 pieces for collection: 1.2 / 0.6 / 0.2 pieces on Tue / Wed / Thu.
        self.assertAlmostEqual(results[TUE].hours["collection"], 1.2 / 100)
        self.assertAlmostEqual(results[WED].hours["collection"], 0.6 / 100)
        self.assertAlmostEqual(results[THU].hours["collection"], 0.2 / 100)
        # The actual pieces collected are still reported as they are.
        self.assertAlmostEqual(results[TUE].items_collected, 300)

    def test_without_one_piece_setting_cushions_use_actual_pieces(self):
        data = {k: v for k, v in SPEC_RATES.items() if k != "one_piece_handling"}
        r = compute_days([MON], {MON: [("cushions", 500)]}, parse_rates(data))[MON]
        self.assertAlmostEqual(r.hours["forklift"], 5)

    def test_one_pallet_per_series_regardless_of_items(self):
        for items in (1, 100, 5000):
            with self.subTest(items=items):
                r = compute_days([MON], {MON: [("cushions", items)]}, self.rates)[MON]
                self.assertAlmostEqual(r.pallets, 1)
        two = compute_days([MON], {MON: [("cushions", 50), ("cushions", 800)]}, self.rates)[MON]
        self.assertAlmostEqual(two.pallets, 2)

    def test_cushion_pallets_leave_with_collection(self):
        results = compute_days(WEEK, {MON: [("cushions", 500)] * 10}, self.rates)  # 10 series = 10 pallets
        # Tue 10 - half of 6 = 7, Wed 4 - half of 3 = 2.5, Thu 1 - half of 1 = 0.5
        self.assertEqual([results[d].pallets for d in WEEK], [10, 7, 2.5, 0.5, 0])
        self.assertEqual([results[d].pallets_awaiting for d in WEEK], [10, 4, 1, 0, 0])
        self.assertEqual([results[d].items_collected for d in WEEK], [0, 3000, 1500, 500, 0])


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.rates = spec_rates()

    def test_60_30_10_over_following_days(self):
        results = compute_days(WEEK, {MON: [("mixed", 1000)]}, self.rates)
        collected = [results[d].items_collected for d in WEEK]
        self.assertEqual(collected, [0, 600, 300, 100, 0])
        awaiting = [results[d].items_awaiting for d in WEEK]
        self.assertEqual(awaiting, [1000, 400, 100, 0, 0])

    def test_collection_hours_with_surcharge_last(self):
        results = compute_days(WEEK, {MON: EXAMPLE_SERIES}, self.rates)
        tue = results[TUE]
        # Tuesday: 280 pallets remain, 168 are collected that day, half of those
        # count as gone during the day: 280 - 84 = 196 = 49 % -> good.
        self.assertAlmostEqual(tue.pallets, 196)
        self.assertEqual(tue.storage_status, GOOD)
        self.assertAlmostEqual(tue.hours["collection"], 8.4)
        self.assertAlmostEqual(tue.total, 8.4)
        wed = results[WED]
        self.assertAlmostEqual(wed.pallets, 112 - 42)
        self.assertAlmostEqual(wed.total, 4.2)
        self.assertAlmostEqual(results[THU].pallets, 28 - 14)
        self.assertAlmostEqual(results[FRI].pallets, 0)

    def test_users_example_100_pallets(self):
        """100 pallets on Monday: 60 collected Tuesday count as 30, so Tuesday shows 70."""
        results = compute_days(WEEK, {MON: [("dsv", 500)]}, self.rates)  # 20 per 100 pcs = 100 pallets
        self.assertEqual([results[d].pallets for d in WEEK], [100, 70, 25, 5, 0])
        # Pallets still waiting at the end of each day are unaffected.
        self.assertEqual([results[d].pallets_awaiting for d in WEEK], [100, 40, 10, 0, 0])

    def test_freed_during_day_zero_means_end_of_day(self):
        data = {**SPEC_RATES, "collection": {"schedule": [0.6, 0.3, 0.1], "freed_during_day": 0}}
        results = compute_days(WEEK, {MON: [("dsv", 500)]}, parse_rates(data))
        self.assertEqual([results[d].pallets for d in WEEK], [100, 100, 40, 10, 0])

    def test_freed_during_day_defaults_to_half(self):
        data = {**SPEC_RATES, "collection": {"schedule": [0.6, 0.3, 0.1]}}
        self.assertEqual(parse_rates(data).freed_during_day, 0.5)

    def test_collection_skips_weekend(self):
        days = [date(2026, 11, d) for d in (16, 17, 18, 19)]
        results = compute_days(days, {FRI: [("dsv", 1000)]}, self.rates)
        self.assertEqual([results[d].items_collected for d in days], [600, 300, 100, 0])

    def test_collection_skips_christmas(self):
        # Wed 23 Dec 2026 -> Thu 24 (open by default), Fri 25 Juledag, Mon 28, Tue 29.
        picked = date(2026, 12, 23)
        days = [date(2026, 12, 24), date(2026, 12, 25), date(2026, 12, 28), date(2026, 12, 29)]
        results = compute_days(days, {picked: [("dsv", 1000)]}, self.rates)
        self.assertEqual(results[date(2026, 12, 25)].closed_reason, "Juledag")
        self.assertEqual(results[date(2026, 12, 25)].total, 0)
        self.assertEqual([results[d].items_collected for d in (days[0], days[2], days[3])], [600, 300, 100])

    def test_collection_skips_extra_closed_day(self):
        rates = spec_rates(extra_closed_days=["12-24"])
        picked = date(2026, 12, 23)
        days = [date(2026, 12, 28), date(2026, 12, 29), date(2026, 12, 30)]
        results = compute_days(days, {picked: [("dsv", 1000)]}, rates)
        self.assertEqual([results[d].items_collected for d in days], [600, 300, 100])

    def test_picks_on_closed_day_are_ignored(self):
        results = compute_days([date(2026, 12, 28)], {date(2026, 12, 25): [("mixed", 1000)]}, self.rates)
        self.assertEqual(results[date(2026, 12, 28)].items_collected, 0)

    def test_lookback_start(self):
        self.assertEqual(lookback_start(MON, self.rates), date(2026, 11, 4))


class StaffingAndPalletTests(unittest.TestCase):
    def setUp(self):
        self.rates = spec_rates()

    def test_employees_from_worked_example(self):
        results = compute_days(WEEK, {MON: EXAMPLE_SERIES}, self.rates)
        self.assertAlmostEqual(results[MON].employees, 76.82 * 1.15 / 7.5)   # 11.78
        self.assertEqual(employees_needed(results[MON].employees), 12)
        self.assertEqual(employees_needed(results[TUE].employees), 2)  # 8.4 h
        self.assertEqual(employees_needed(results[FRI].employees), 0)

    def test_whole_days_are_not_rounded_up(self):
        self.assertEqual(employees_needed(15 / 7.5), 2)
        self.assertEqual(employees_needed(2.0000000001), 2)

    def test_custom_working_day(self):
        data = {**SPEC_RATES, "staffing": {"hours_per_employee": 8}}
        r = compute_days([MON], {MON: EXAMPLE_SERIES}, parse_rates(data))[MON]
        self.assertAlmostEqual(r.employees, 76.82 * 1.15 / 8)

    def test_pallets_awaiting_collection(self):
        results = compute_days(WEEK, {MON: EXAMPLE_SERIES}, self.rates)
        self.assertEqual([results[d].pallets_awaiting for d in WEEK], [280, 112, 28, 0, 0])


class StorageThresholdTests(unittest.TestCase):
    def setUp(self):
        self.rates = spec_rates()

    def status(self, items):
        # DSV: 20 pallets per 100 pcs, so 5 pcs = 1 pallet.
        r = compute_days([MON], {MON: [("dsv", items)]}, self.rates)[MON]
        return r.storage_status, r.surcharge_rate

    def test_thresholds(self):
        self.assertEqual(self.status(1200), (GOOD, 0))           # 240 pallets = 60 %
        self.assertEqual(self.status(1205), (TIGHT, 0.15))
        self.assertEqual(self.status(1600), (TIGHT, 0.15))       # 320 pallets = 80 %
        self.assertEqual(self.status(1605), (VERY_TIGHT, 0.25))
        self.assertEqual(self.status(2000), (VERY_TIGHT, 0.25))  # 400 pallets, exactly full
        self.assertEqual(self.status(2005), (OVER, 0.30))

    def test_three_levels_each_use_their_own_surcharge(self):
        data = copy.deepcopy(SPEC_RATES)
        data["storage"].update(tight_surcharge=0.10, very_tight_surcharge=0.15, over_capacity_surcharge=0.20)
        rates = parse_rates(data)
        for items, expected in [(1200, (GOOD, 0)), (1205, (TIGHT, 0.10)),
                                (1605, (VERY_TIGHT, 0.15)), (2005, (OVER, 0.20))]:
            with self.subTest(items=items):
                r = compute_days([MON], {MON: [("dsv", items)]}, rates)[MON]
                self.assertEqual((r.storage_status, r.surcharge_rate), expected)
                self.assertAlmostEqual(r.hours["surcharge"], r.subtotal * expected[1])

    def test_missing_over_capacity_setting_falls_back_to_very_tight(self):
        data = copy.deepcopy(SPEC_RATES)
        del data["storage"]["over_capacity_surcharge"]
        self.assertEqual(parse_rates(data).over_capacity_surcharge, 0.25)

    def test_over_capacity_from_accumulated_days(self):
        results = compute_days([TUE], {MON: [("mixed", 1200)], TUE: [("mixed", 1200)]}, self.rates)
        tue = results[TUE]
        # Tuesday's 264 + Monday's 264 minus half of the 158.4 collected = 448.8 (112 %)
        self.assertAlmostEqual(tue.pallets, 448.8)
        self.assertEqual(tue.storage_status, OVER)
        # Picking 36, forklift 12, wrapping 18, booking 4.2, labeling 3.6, collection 7.2; +30 % over capacity
        self.assertAlmostEqual(tue.total, (36 + 12 + 18 + 4.2 + 3.6 + 7.2) * 1.30)


if __name__ == "__main__":
    unittest.main()
