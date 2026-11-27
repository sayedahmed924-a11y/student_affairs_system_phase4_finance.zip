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
            reverse("students:download_backup", kwargs={"filename": "not-a-backup.txt"})
        )
        self.assertEqual(response.status_code, 404)


from django.contrib.auth.models import Permission
from django.http import HttpResponse
from django.test import RequestFactory

from .audit_middleware import SystemAuditMiddleware
from .models import SystemAuditEvent


class CentralAuditTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="audit_operator",
            password="Strong-Audit-Password-123!",
        )
        self.factory = RequestFactory()

    def test_successful_authenticated_write_is_logged(self):
        request = self.factory.post(
            "/students/finance/payments/add/",
            REMOTE_ADDR="192.168.1.25",
            HTTP_USER_AGENT="LAN Workstation",
        )
        request.user = self.user
        middleware = SystemAuditMiddleware(lambda _request: HttpResponse(status=302))
        response = middleware(request)

        self.assertEqual(response.status_code, 302)
        event = SystemAuditEvent.objects.get()
        self.assertEqual(event.actor_username, "audit_operator")
        self.assertEqual(event.module, "finance")
        self.assertEqual(event.method, "POST")
        self.assertEqual(event.ip_address, "192.168.1.25")
        self.assertEqual(event.user_agent, "LAN Workstation")
        self.assertEqual(event.status_code, 302)

    def test_read_request_is_not_logged(self):
        request = self.factory.get("/students/finance/")
        request.user = self.user
        middleware = SystemAuditMiddleware(lambda _request: HttpResponse(status=200))
        middleware(request)
        self.assertEqual(SystemAuditEvent.objects.count(), 0)

    def test_failed_request_is_not_logged(self):
        request = self.factory.post("/students/finance/payments/add/")
        request.user = self.user
        middleware = SystemAuditMiddleware(lambda _request: HttpResponse(status=400))
        middleware(request)
        self.assertEqual(SystemAuditEvent.objects.count(), 0)

    def test_central_log_page_requires_permission(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("students:system_audit"))
        self.assertEqual(response.status_code, 403)

        permission = Permission.objects.get(
            content_type__app_label="students",
            codename="view_systemauditevent",
        )
        self.user.user_permissions.add(permission)
        response = self.client.get(reverse("students:system_audit"))
        self.assertEqual(response.status_code, 200)
