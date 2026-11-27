import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError

from students.models import Student


class Command(BaseCommand):
    help = "Create synthetic demo students and a read-only demo account."

    def handle(self, *args, **options):
        password = os.getenv("DEMO_PASSWORD", "")
        if len(password) < 12:
            raise CommandError("Set DEMO_PASSWORD to a value of at least 12 characters.")

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username="demo_viewer",
            defaults={"is_active": True, "is_staff": False, "is_superuser": False},
        )
        user.is_active = True
        user.is_staff = False
        user.is_superuser = False
        user.set_password(password)
        user.save()

        group, _ = Group.objects.get_or_create(name="Demo - Read Only")
        permission = Permission.objects.get(
            content_type__app_label="students",
            codename="view_student",
        )
        group.permissions.set([permission])
        user.groups.set([group])

        demo_rows = [
            ("DEMO-1001", "طالب تجريبي - أحمد"),
            ("DEMO-1002", "طالبة تجريبية - مريم"),
            ("DEMO-1003", "طالب تجريبي - يوسف"),
        ]
        for university_id, full_name in demo_rows:
            Student.objects.get_or_create(
                university_id=university_id,
                defaults={"full_name": full_name, "nationality": "بيانات تجريبية"},
            )

        self.stdout.write(self.style.SUCCESS(
            "Demo data ready. Login username: demo_viewer. Password is the DEMO_PASSWORD environment value."
        ))
