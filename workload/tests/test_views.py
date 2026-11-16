"""Page-level tests. Run with `python manage.py test`."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from workload.models import PickSeries

from .helpers import TEST_RATES_PATH

User = get_user_model()
PASSWORD = "Lager-Test-2026!"
WEEK_DAYS = ["20261109", "20261110", "20261111", "20261112", "20261113"]  # week 46, 2026


def empty_week_post() -> dict:
    data = {}
    for d in WEEK_DAYS:
        p = f"d{d}"
        data.update({
            f"{p}-TOTAL_FORMS": "0",
            f"{p}-INITIAL_FORMS": "0",
            f"{p}-MIN_NUM_FORMS": "0",
            f"{p}-MAX_NUM_FORMS": "1000",
        })
    return data


@override_settings(WORKLOAD_RATES_PATH=TEST_RATES_PATH)
class WeekPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.viewer = User.objects.create_user("laeser", password=PASSWORD)
        cls.admin = User.objects.create_user("planlaegger", password=PASSWORD, is_staff=True)

    def test_login_required(self):
        response = self.client.get(reverse("week", args=[2026, 46]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_login_page(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, "Log ind")

    def test_home_redirects_to_a_week(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/uge/", response["Location"])

    def test_viewer_sees_week_but_cannot_edit(self):
        PickSeries.objects.create(date=date(2026, 11, 9), series_type="mixed", items=1000)
        PickSeries.objects.create(date=date(2026, 11, 9), series_type="large_same", items=400)
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("week", args=[2026, 46]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mandag")
        self.assertContains(response, "88,3")  # Monday total from the worked example
        self.assertContains(response, "Stram")
        self.assertContains(response, "Stk. til pluk i denne uge")
        self.assertContains(response, "Udlevering")
        self.assertContains(response, "Medarbejdere")
        self.assertContains(response, "Lagerplads")
        self.assertContains(response, "1.400 <span class=\"muted\">(ca. 378 pll)</span>", html=False)
        self.assertNotContains(response, "% · ")
        self.assertNotContains(response, "fventer")
        self.assertContains(response, "Strækfilm")
        self.assertContains(response, "inkl. +15 % pladsmangeltillæg</div>")
        self.assertNotContains(response, "agertillæg")
        self.assertNotContains(response, reverse("week_edit", args=[2026, 46]))
        self.assertEqual(self.client.get(reverse("week_edit", args=[2026, 46])).status_code, 403)

    def test_nonexistent_week_is_404(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse("week", args=[2025, 53])).status_code, 404)

    def test_year_calendar(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("year", args=[2026]))
        self.assertContains(response, "November")
        self.assertContains(response, reverse("week", args=[2026, 46]))

    def test_admin_adds_series(self):
        self.client.force_login(self.admin)
        url = reverse("week_edit", args=[2026, 46])
        self.assertEqual(self.client.get(url).status_code, 200)
        data = empty_week_post()
        data.update({
            "d20261109-TOTAL_FORMS": "2",
            "d20261109-0-id": "", "d20261109-0-series_type": "dsv", "d20261109-0-items": "250",
            "d20261109-1-id": "", "d20261109-1-series_type": "", "d20261109-1-items": "",  # empty row is ignored
        })
        response = self.client.post(url, data)
        self.assertRedirects(response, reverse("week", args=[2026, 46]))
        series = PickSeries.objects.get()
        self.assertEqual((series.date, series.series_type, series.items), (date(2026, 11, 9), "dsv", 250))
        self.assertEqual(series.updated_by, self.admin)

    def test_admin_edits_and_deletes_series(self):
        keep = PickSeries.objects.create(date=date(2026, 11, 10), series_type="mixed", items=10)
        drop = PickSeries.objects.create(date=date(2026, 11, 10), series_type="dsv", items=20)
        self.client.force_login(self.admin)
        data = empty_week_post()
        data.update({
            "d20261110-TOTAL_FORMS": "2", "d20261110-INITIAL_FORMS": "2",
            "d20261110-0-id": str(keep.pk), "d20261110-0-series_type": "mixed", "d20261110-0-items": "15",
            "d20261110-1-id": str(drop.pk), "d20261110-1-series_type": "dsv", "d20261110-1-items": "20",
            "d20261110-1-DELETE": "on",
        })
        response = self.client.post(reverse("week_edit", args=[2026, 46]), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(PickSeries.objects.values_list("pk", "items")), [(keep.pk, 15)])

    def test_admin_adds_cushion_series(self):
        self.client.force_login(self.admin)
        url = reverse("week_edit", args=[2026, 46])
        self.assertContains(self.client.get(url), "Hynder")
        data = empty_week_post()
        data.update({
            "d20261112-TOTAL_FORMS": "1",
            "d20261112-0-id": "", "d20261112-0-series_type": "cushions", "d20261112-0-items": "300",
        })
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(PickSeries.objects.get().get_series_type_display(), "Hynder")

    def test_invalid_input_is_not_saved(self):
        self.client.force_login(self.admin)
        data = empty_week_post()
        data.update({
            "d20261111-TOTAL_FORMS": "1",
            "d20261111-0-id": "", "d20261111-0-series_type": "mixed", "d20261111-0-items": "0",
        })
        response = self.client.post(reverse("week_edit", args=[2026, 46]), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PickSeries.objects.exists())


@override_settings(WORKLOAD_RATES_PATH=TEST_RATES_PATH)
class UserManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_superuser("ejer", password=PASSWORD)
        cls.admin = User.objects.create_user("planlaegger", password=PASSWORD, is_staff=True)
        cls.viewer = User.objects.create_user("laeser", password=PASSWORD)

    def test_viewer_cannot_manage_users(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse("user_list")).status_code, 403)

    def test_admin_creates_viewer(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("user_create"), {
            "username": "ny", "first_name": "Ny", "last_name": "Bruger",
            "password1": "Helt-Ny-Kode-77", "password2": "Helt-Ny-Kode-77",
        })
        self.assertRedirects(response, reverse("user_list"))
        user = User.objects.get(username="ny")
        self.assertFalse(user.is_staff)
        self.assertTrue(user.check_password("Helt-Ny-Kode-77"))

    def test_admin_resets_password(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("user_password", args=[self.viewer.pk]), {
            "new_password1": "Nulstillet-Kode-88", "new_password2": "Nulstillet-Kode-88",
        })
        self.assertRedirects(response, reverse("user_list"))
        self.viewer.refresh_from_db()
        self.assertTrue(self.viewer.check_password("Nulstillet-Kode-88"))

    def test_admin_cannot_touch_owner(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("user_edit", args=[self.owner.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("user_password", args=[self.owner.pk])).status_code, 403)

    def test_admin_cannot_demote_or_deactivate_self(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("user_edit", args=[self.admin.pk]), {
            "first_name": "Plan", "last_name": "Lægger", "is_staff": "", "is_active": "",
        })
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_staff)
        self.assertTrue(self.admin.is_active)
        self.assertEqual(self.admin.first_name, "Plan")
