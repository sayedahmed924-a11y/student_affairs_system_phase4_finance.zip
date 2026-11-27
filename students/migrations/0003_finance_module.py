import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("students", "0002_course_grading_settings"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="StudentCharge",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=180, verbose_name="بيان الاستحقاق")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, verbose_name="قيمة الاستحقاق")),
                ("due_date", models.DateField(blank=True, null=True, verbose_name="تاريخ الاستحقاق")),
                ("notes", models.TextField(blank=True, verbose_name="ملاحظات")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")),
                ("is_cancelled", models.BooleanField(default=False, verbose_name="ملغي")),
                ("cancellation_reason", models.TextField(blank=True, verbose_name="سبب الإلغاء")),
                ("cancelled_at", models.DateTimeField(blank=True, null=True, verbose_name="تاريخ الإلغاء")),
                ("cancelled_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="cancelled_student_charges", to=settings.AUTH_USER_MODEL)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_student_charges", to=settings.AUTH_USER_MODEL)),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="charges", to="students.student", verbose_name="الطالب")),
                ("term", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="charges", to="students.academicterm", verbose_name="الفصل الدراسي")),
            ],
            options={"verbose_name": "استحقاق مالي", "verbose_name_plural": "الاستحقاقات المالية", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="PaymentReceipt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("receipt_number", models.CharField(max_length=60, unique=True, verbose_name="رقم الإيصال")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, verbose_name="المبلغ المدفوع")),
                ("method", models.CharField(choices=[("cash", "نقدي"), ("bank", "تحويل بنكي"), ("card", "بطاقة"), ("other", "أخرى")], default="cash", max_length=10, verbose_name="طريقة الدفع")),
                ("reference", models.CharField(blank=True, max_length=120, verbose_name="رقم مرجعي")),
                ("notes", models.TextField(blank=True, verbose_name="ملاحظات")),
                ("received_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name="تاريخ ووقت السداد")),
                ("is_voided", models.BooleanField(default=False, verbose_name="ملغي")),
                ("void_reason", models.TextField(blank=True, verbose_name="سبب الإلغاء")),
                ("voided_at", models.DateTimeField(blank=True, null=True, verbose_name="تاريخ إلغاء الإيصال")),
                ("charge", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payments", to="students.studentcharge", verbose_name="الاستحقاق")),
                ("received_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="student_payment_receipts", to=settings.AUTH_USER_MODEL)),
                ("voided_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="voided_student_receipts", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "إيصال سداد", "verbose_name_plural": "إيصالات السداد", "ordering": ["-received_at"]},
        ),
        migrations.AddConstraint(model_name="studentcharge", constraint=models.CheckConstraint(condition=models.Q(("amount__gt", 0)), name="student_charge_amount_positive")),
        migrations.AddConstraint(model_name="paymentreceipt", constraint=models.CheckConstraint(condition=models.Q(("amount__gt", 0)), name="payment_receipt_amount_positive")),
    ]
