from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase, TransactionTestCase
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
from .models import SystemAuditEvent, Student


class CentralAuditTests(TransactionTestCase):
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
        def save_student(_request):
            Student.objects.create(university_id="AUD-001", full_name="طالب اختبار")
            return HttpResponse(status=302)

        middleware = SystemAuditMiddleware(save_student)
        response = middleware(request)

        self.assertEqual(response.status_code, 302)
        event = SystemAuditEvent.objects.get()
        self.assertEqual(event.actor_username, "audit_operator")
        self.assertEqual(event.module, "students")
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



from decimal import Decimal
from datetime import timedelta
from .models import StudentCharge, PaymentReceipt
from .forms import PaymentReceiptForm


class ConcurrentStudentEditTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="student_editor",
            password="Strong-Student-Edit-123!",
        )
        permission = Permission.objects.get(
            content_type__app_label="students",
            codename="change_student",
        )
        self.user.user_permissions.add(permission)
        self.student = Student.objects.create(
            university_id="CONC-001",
            full_name="الاسم الأصلي",
        )
        self.client.force_login(self.user)

    def test_stale_form_cannot_overwrite_newer_student_data(self):
        page = self.client.get(reverse("students:edit", kwargs={"pk": self.student.pk}))
        self.assertEqual(page.status_code, 200)
        stale_token = page.context["form"]["version_token"].value()

        Student.objects.filter(pk=self.student.pk).update(
            full_name="تعديل الموظف الأول",
            updated_at=self.student.updated_at + timedelta(seconds=5),
        )
        self.student.refresh_from_db()

        response = self.client.post(
            reverse("students:edit", kwargs={"pk": self.student.pk}),
            {
                "version_token": stale_token,
                "university_id": self.student.university_id,
                "full_name": "تعديل الموظف الثاني",
                "national_id": "",
                "nationality": "مصري",
                "phone": "",
                "address": "",
                "academic_year": "",
                "department": "",
                "division": "",
                "study_status": "new",
                "notes": "",
                "reason": "اختبار تعارض التعديل",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.full_name, "تعديل الموظف الأول")
        self.assertContains(response, "تم تعديل بيانات هذا الطالب بواسطة موظف آخر")

    def test_current_version_can_be_saved(self):
        page = self.client.get(reverse("students:edit", kwargs={"pk": self.student.pk}))
        token = page.context["form"]["version_token"].value()
        response = self.client.post(
            reverse("students:edit", kwargs={"pk": self.student.pk}),
            {
                "version_token": token,
                "university_id": self.student.university_id,
                "full_name": "اسم محدث",
                "national_id": "",
                "nationality": "مصري",
                "phone": "",
                "address": "",
                "academic_year": "",
                "department": "",
                "division": "",
                "study_status": "new",
                "notes": "",
                "reason": "تعديل صحيح",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.student.refresh_from_db()
        self.assertEqual(self.student.full_name, "اسم محدث")


class FinancialIntegrityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="finance_operator",
            password="Strong-Finance-123!",
        )
        self.student = Student.objects.create(
            university_id="FIN-001",
            full_name="طالب مالي",
        )
        self.charge = StudentCharge.objects.create(
            student=self.student,
            title="رسوم اختبار",
            amount=Decimal("100.00"),
            created_by=self.user,
        )

    def test_receipt_number_is_unique(self):
        PaymentReceipt.objects.create(
            charge=self.charge,
            receipt_number="REC-UNIQUE-001",
            amount=Decimal("25.00"),
            received_by=self.user,
        )
        form = PaymentReceiptForm(data={
            "charge": self.charge.pk,
            "receipt_number": "REC-UNIQUE-001",
            "amount": "10.00",
            "method": "cash",
            "reference": "",
            "notes": "",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("receipt_number", form.errors)

    def test_non_positive_payment_is_rejected(self):
        form = PaymentReceiptForm(data={
            "charge": self.charge.pk,
            "receipt_number": "REC-ZERO-001",
            "amount": "0.00",
            "method": "cash",
            "reference": "",
            "notes": "",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("amount", form.errors)


class BackupRetentionTests(TestCase):
    def test_retention_removes_oldest_complete_sets_as_pairs(self):
        import os
        import tempfile
        from pathlib import Path
        from django.core.management import CommandError
        from students.management.commands.backup_database import prune_backups

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stamps = ["20260101_010101", "20260102_010101", "20260103_010101"]
            for stamp in stamps:
                (root / f"student_affairs_{stamp}.dump").write_bytes(b"database")
                (root / f"student_affairs_{stamp}_media.tar.gz").write_bytes(b"media")

            # Keep the newest two complete sets.
            now = __import__("time").time()
            for index, stamp in enumerate(stamps):
                moment = now - (len(stamps) - index) * 60
                for suffix in (".dump", "_media.tar.gz"):
                    os.utime(root / f"student_affairs_{stamp}{suffix}", (moment, moment))

            # An unrelated file must never be removed by retention.
            unrelated = root / "important.txt"
            unrelated.write_text("keep", encoding="utf-8")

            removed = prune_backups(root, retention_days=365, retention_count=2)

            self.assertEqual(removed, 2)
            self.assertFalse((root / f"student_affairs_{stamps[0]}.dump").exists())
            self.assertFalse((root / f"student_affairs_{stamps[0]}_media.tar.gz").exists())
            self.assertTrue((root / f"student_affairs_{stamps[1]}.dump").exists())
            self.assertTrue((root / f"student_affairs_{stamps[2]}_media.tar.gz").exists())
            self.assertTrue(unrelated.exists())

    def test_incomplete_backup_set_is_not_pruned(self):
        import tempfile
        from pathlib import Path
        from students.management.commands.backup_database import prune_backups

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            orphan = root / "student_affairs_20260101_010101.dump"
            orphan.write_bytes(b"database")
            prune_backups(root, retention_days=1, retention_count=1)
            self.assertTrue(orphan.exists())
