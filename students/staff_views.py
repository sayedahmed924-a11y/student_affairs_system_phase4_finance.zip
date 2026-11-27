from django import forms
from django.contrib import messages
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import Group, Permission
from .models import Student
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

User = get_user_model()

# Built-in Django groups and permissions: no custom database tables or migrations.
ROLE_DEFINITIONS = {
    "مدير شؤون الطلاب": {
        "label": "مدير شؤون الطلاب بصلاحيات تشغيلية كاملة",
        "permissions": [
            "view_student", "add_student", "change_student", "export_reports", "print_reports",
            "view_importbatch", "add_importbatch", "change_importbatch",
            "view_auditlog", "view_academicterm", "add_academicterm", "change_academicterm",
            "view_course", "add_course", "change_course",
            "view_studentenrollment", "add_studentenrollment", "change_studentenrollment",
            "view_courseregistration", "add_courseregistration", "change_courseregistration",
            "view_studentacademicevent", "add_studentacademicevent",
            "view_studentcharge", "add_studentcharge", "change_studentcharge",
            "view_paymentreceipt", "add_paymentreceipt", "change_paymentreceipt",
        ],
    },
    "شؤون التسجيل": {
        "label": "موظف شؤون الطلاب والتسجيل",
        "permissions": [
            "view_student", "add_student", "change_student",
            "view_importbatch", "add_importbatch", "change_importbatch",
            "view_auditlog", "view_academicterm", "view_course",
            "view_studentenrollment", "add_studentenrollment",
            "view_courseregistration", "view_studentacademicevent",
            "add_studentacademicevent",
        ],
    },
    "الشؤون الأكاديمية": {
        "label": "موظف الشؤون الأكاديمية ورصد النتائج",
        "permissions": [
            "view_student", "view_academicterm", "add_academicterm", "view_course", "add_course",
            "view_studentenrollment", "add_studentenrollment",
            "view_courseregistration", "add_courseregistration",
            "change_courseregistration", "view_studentacademicevent",
            "add_studentacademicevent", "view_auditlog",
        ],
    },
    "الإدارة المالية": {
        "label": "موظف الإدارة المالية",
        "permissions": [
            "view_student", "view_studentcharge", "add_studentcharge",
            "change_studentcharge", "view_paymentreceipt",
            "add_paymentreceipt", "change_paymentreceipt", "export_reports", "print_reports",
        ],
    },
    "مراجع التقارير": {
        "label": "مراجع التقارير والإحصائيات",
        "permissions": [
            "view_student", "view_studentenrollment",
            "view_courseregistration", "view_studentcharge",
            "view_paymentreceipt", "view_auditlog",
            "view_studentacademicevent", "export_reports", "print_reports",
        ],
    },
    "استعلام فقط": {
        "label": "موظف استعلام وقراءة فقط",
        "permissions": [
            "view_student", "view_academicterm", "view_course",
            "view_studentenrollment", "view_courseregistration",
            "view_studentacademicevent", "view_studentcharge",
            "view_paymentreceipt",
        ],
    },
}


def _is_superuser(user):
    return user.is_authenticated and user.is_active and user.is_superuser


def _ensure_roles():
    student_type = ContentType.objects.get_for_model(Student)
    Permission.objects.get_or_create(
        content_type=student_type, codename="export_reports",
        defaults={"name": "Can export reports to Excel"},
    )
    Permission.objects.get_or_create(
        content_type=student_type, codename="print_reports",
        defaults={"name": "Can print reports and receipts"},
    )
    app_permissions = Permission.objects.filter(content_type__app_label="students")
    by_code = {permission.codename: permission for permission in app_permissions}
    groups = []
    for name, definition in ROLE_DEFINITIONS.items():
        group, _ = Group.objects.get_or_create(name=name)
        group.permissions.set([
            by_code[code] for code in definition["permissions"] if code in by_code
        ])
        groups.append(group)
    return groups


@user_passes_test(_is_superuser, login_url="login")
def staff_access(request):
    groups = _ensure_roles()
    selected_user = None
    if request.method == "POST":
        user_id = request.POST.get("user_id", "").strip()
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        password = request.POST.get("password", "")
        is_active = request.POST.get("is_active") == "on"
        group_ids = request.POST.getlist("groups")

        if not username:
            messages.error(request, "اسم المستخدم مطلوب.")
        elif User.objects.filter(username__iexact=username).exclude(pk=user_id or None).exists():
            messages.error(request, "اسم المستخدم مستخدم بالفعل.")
        else:
            try:
                with transaction.atomic():
                    if user_id:
                        target = get_object_or_404(User.objects.select_for_update(), pk=user_id, is_superuser=False)
                        action_flag = CHANGE
                    else:
                        target = User()
                        action_flag = ADDITION
                    target.username = username
                    target.email = email
                    target.first_name = first_name
                    target.last_name = last_name
                    target.is_active = is_active
                    # Application staff are not Django-admin staff.
                    target.is_staff = False
                    if password:
                        validate_password(password, user=target)
                        target.set_password(password)
                    elif not user_id:
                        raise ValidationError("كلمة المرور مطلوبة عند إنشاء حساب جديد.")
                    target.save()
                    target.groups.set(Group.objects.filter(pk__in=group_ids, name__in=ROLE_DEFINITIONS.keys()))
                    target.user_permissions.clear()
                    LogEntry.objects.create(
                        user=request.user,
                        content_type=ContentType.objects.get_for_model(User),
                        object_id=str(target.pk),
                        object_repr=target.username,
                        action_flag=action_flag,
                        change_message="إنشاء أو تحديث حساب موظف وصلاحياته من شاشة إدارة الصلاحيات.",
                    )
                messages.success(request, "تم حفظ حساب الموظف ومجموعات الصلاحيات.")
                return redirect("students:staff_access")
            except ValidationError as exc:
                messages.error(request, "تعذر حفظ الحساب: " + " ".join(exc.messages))
    elif request.GET.get("edit"):
        selected_user = get_object_or_404(User, pk=request.GET["edit"], is_superuser=False)

    staff_users = User.objects.filter(is_superuser=False).prefetch_related("groups").order_by("username")
    return render(request, "students/staff_access.html", {
        "groups": groups,
        "role_definitions": ROLE_DEFINITIONS,
        "staff_users": staff_users,
        "selected_user": selected_user,
    })
