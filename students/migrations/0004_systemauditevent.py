from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("students", "0003_finance_module"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SystemAuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("actor_username", models.CharField(db_index=True, max_length=150, verbose_name="اسم المستخدم وقت العملية")),
                ("module", models.CharField(choices=[("students", "شؤون الطلاب"), ("academic", "الشؤون الأكاديمية"), ("finance", "الإدارة المالية"), ("imports", "استيراد البيانات"), ("users", "المستخدمون والصلاحيات"), ("backups", "النسخ الاحتياطي"), ("system", "النظام")], db_index=True, max_length=20, verbose_name="القسم")),
                ("action", models.CharField(max_length=100, verbose_name="العملية")),
                ("path", models.CharField(max_length=500, verbose_name="مسار العملية")),
                ("object_reference", models.CharField(blank=True, max_length=120, verbose_name="مرجع السجل")),
                ("method", models.CharField(max_length=10, verbose_name="طريقة الطلب")),
                ("status_code", models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="كود الاستجابة")),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True, verbose_name="عنوان الجهاز")),
                ("user_agent", models.CharField(blank=True, max_length=500, verbose_name="معلومات الجهاز والمتصفح")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="تاريخ ووقت العملية")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="system_audit_events", to=settings.AUTH_USER_MODEL, verbose_name="الموظف")),
            ],
            options={
                "verbose_name": "عملية بالنظام",
                "verbose_name_plural": "سجل العمليات المركزي",
                "ordering": ["-created_at"],
                "indexes": [models.Index(fields=["module", "-created_at"], name="sysaudit_module_date")],
            },
        ),
    ]
