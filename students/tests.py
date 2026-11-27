from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from .staff_views import _ensure_roles

User = get_user_model()


class StaffAccessTests(TestCase):
    def test_role_groups_and_custom_permissions_are_created(self):
        _ensure_roles()

        finance = Group.objects.get(name="الإدارة المالية")
        read_only = Group.objects.get(name="استعلام فقط")
        manager = Group.objects.get(name="مدير شؤون الطلاب")

        export_permission = Permission.objects.get(
            codename="export_reports",
            content_type__app_label="students",
        )
        print_permission = Permission.objects.get(
            codename="print_reports",
            content_type__app_label="students",
        )

        self.assertTrue(finance.permissions.filter(pk=export_permission.pk).exists())
        self.assertTrue(finance.permissions.filter(pk=print_permission.pk).exists())
        self.assertFalse(read_only.permissions.filter(pk=export_permission.pk).exists())
        self.assertFalse(read_only.permissions.filter(pk=print_permission.pk).exists())
        self.assertTrue(manager.permissions.filter(pk=export_permission.pk).exists())

    def test_staff_access_is_restricted_to_superusers(self):
        employee = User.objects.create_user(
            username="employee_test",
            password="Strong-Test-Password-123!",
            is_staff=False,
        )
        self.client.force_login(employee)
        response = self.client.get(reverse("students:staff_access"))
        self.assertEqual(response.status_code, 302)

        administrator = User.objects.create_superuser(
            username="admin_test",
            email="admin@example.invalid",
            password="Strong-Admin-Password-123!",
        )
        self.client.force_login(administrator)
        response = self.client.get(reverse("students:staff_access"))
        self.assertEqual(response.status_code, 200)


class BackupAccessTests(TestCase):
    def test_backup_dashboard_is_superuser_only(self):
        employee = User.objects.create_user(
            username="backup_employee",
            password="Strong-Backup-Password-123!",
            is_staff=False,
        )
        self.client.force_login(employee)
        response = self.client.get(reverse("students:backup_dashboard"))
        self.assertEqual(response.status_code, 302)

        administrator = User.objects.create_superuser(
            username="backup_admin",
            email="backup-admin@example.invalid",
            password="Strong-Backup-Admin-123!",
        )
        self.client.force_login(administrator)
        response = self.client.get(reverse("students:backup_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_backup_download_rejects_invalid_filename(self):
        administrator = User.objects.create_superuser(
            username="backup_download_admin",
            email="backup-download@example.invalid",
            password="Strong-Backup-Admin-123!",
        )
        self.client.force_login(administrator)
        response = self.client.get(
            reverse("students:download_backup", kwargs={"filename": "../db.sqlite3"})
        )
        self.assertEqual(response.status_code, 404)
