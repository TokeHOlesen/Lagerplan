"""Shared test fixtures (pure Python)."""

from pathlib import Path

from workload.ratesconfig import parse_rates

# Fixed rates for the tests (the values below, as a file). The app's live
# rates.toml can be tuned freely without affecting the tests.
TEST_RATES_PATH = str(Path(__file__).resolve().parent / "rates_test.toml")

SPEC_RATES = {
    "pick_series": {"mixed": 3.0, "dsv": 2.0, "large_mixed": 1.5, "large_same": 1.0, "cushions": 1.2},
    "handling": {"forklift": 1.0, "wrapping": 1.5, "booking": 0.2, "labeling": 0.3, "collection": 1.0},
    "collection": {"schedule": [0.6, 0.3, 0.1], "freed_during_day": 0.5},
    "pallets_per_100": {"mixed": 22, "dsv": 20, "large_mixed": 18, "large_same": 15},
    "pallets_per_series": {"cushions": 1},
    "task_overrides": {"booking": {
        "mixed": {"per_100": 0.35},
        "dsv": {"per_series": 0.12},
        "large_mixed": {"per_series": 0.12},
        "large_same": {"per_series": 0.12},
        "cushions": {"per_series": 0.12},
    }},
    "one_piece_handling": {"cushions": ["forklift", "wrapping", "booking", "labeling", "collection"]},
    "pallet_estimate": {"per_100": 27, "per_series": {"cushions": 1}},
    "storage": {
        "capacity": 400,
        "tight_above": 0.6,
        "very_tight_above": 0.8,
        "tight_surcharge": 0.15,
        "very_tight_surcharge": 0.25,
        "over_capacity_surcharge": 0.30,
    },
}

# Worked example used across the tests: Monday, empty warehouse,
#   1,000 pcs Mixed + 400 pcs Large same items = 1,400 pcs.
#   Picking 30 + 4 = 34 h; forklift 14, wrapping 21, labeling 4.2 h.
#   Booking: 1,000 x 0.35 / 100 = 3.5 h (mixed) + 0.12 h (one large series) = 3.62 h.
#   Subtotal 76.82 h. Pallets 220 + 60 = 280 = 70 % of 400 -> tight, +15 % = 11.523 h.
#   Total 88.343 h = 11.78 employees -> 12.
EXAMPLE_SERIES = [("mixed", 1000), ("large_same", 400)]


def spec_rates(**calendar):
    data = {**SPEC_RATES}
    if calendar:
        data["calendar"] = calendar
    return parse_rates(data)
