from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("students", "0004_systemauditevent"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="student",
            name="financial_code",
            field=models.CharField(blank=True, db_index=True, max_length=60, verbose_name="الكود المالي"),
        ),
        migrations.AddField(
            model_name="student",
            name="program",
            field=models.CharField(blank=True, db_index=True, max_length=120, verbose_name="البرنامج"),
        ),
        migrations.CreateModel(
            name="FeeCatalog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category", models.CharField(choices=[("ministry", "رسوم الوزارة"), ("expat_club", "رسوم نادي الوافدين"), ("dollar_services", "الخدمات الدولارية"), ("other", "خدمات أخرى")], db_index=True, max_length=24, verbose_name="فئة الرسوم")),
                ("name", models.CharField(db_index=True, max_length=180, verbose_name="نوع الخدمة")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, verbose_name="قيمة الخدمة")),
                ("currency", models.CharField(choices=[("USD", "دولار أمريكي"), ("EGP", "جنيه مصري")], max_length=3, verbose_name="العملة")),
                ("amount_words", models.CharField(blank=True, max_length=300, verbose_name="المبلغ بالحروف")),
                ("bank_name", models.CharField(blank=True, max_length=180, verbose_name="اسم البنك")),
                ("source_workbook", models.CharField(blank=True, max_length=255, verbose_name="ملف المصدر")),
                ("source_sheet", models.CharField(blank=True, max_length=180, verbose_name="ورقة المصدر")),
                ("is_active", models.BooleanField(default=True, verbose_name="نشط")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="آخر تحديث")),
            ],
            options={"verbose_name": "بند رسوم/خدمة", "verbose_name_plural": "دليل الرسوم والخدمات", "ordering": ["category", "name", "amount"]},
        ),
        migrations.AddConstraint(
            model_name="feecatalog",
            constraint=models.UniqueConstraint(fields=("category", "name", "amount", "currency"), name="uniq_fee_category_name_amount_currency"),
        ),
        migrations.CreateModel(
            name="SupplyOrder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("order_number", models.CharField(blank=True, db_index=True, max_length=100, verbose_name="رقم أمر التوريد")),
                ("category", models.CharField(choices=[("ministry", "رسوم الوزارة"), ("expat_club", "رسوم نادي الوافدين"), ("dollar_services", "الخدمات الدولارية"), ("other", "خدمات أخرى")], db_index=True, max_length=24, verbose_name="فئة أمر التوريد")),
                ("currency", models.CharField(choices=[("USD", "دولار أمريكي"), ("EGP", "جنيه مصري")], max_length=3, verbose_name="العملة")),
                ("bank_name", models.CharField(blank=True, max_length=180, verbose_name="اسم البنك")),
                ("total_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="إجمالي أمر التوريد")),
                ("amount_words", models.CharField(blank=True, max_length=400, verbose_name="الإجمالي بالحروف")),
                ("source_workbook", models.CharField(max_length=255, verbose_name="ملف المصدر")),
                ("source_sheet", models.CharField(blank=True, max_length=180, verbose_name="ورقة المصدر")),
                ("imported_at", models.DateTimeField(auto_now_add=True)),
                ("notes", models.TextField(blank=True, verbose_name="ملاحظات")),
                ("imported_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "أمر توريد", "verbose_name_plural": "أوامر التوريد", "ordering": ["-imported_at"]},
        ),
        migrations.CreateModel(
            name="SupplyOrderLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("service_name", models.CharField(blank=True, max_length=180, verbose_name="بيان الخدمة")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, verbose_name="المبلغ")),
                ("currency", models.CharField(choices=[("USD", "دولار أمريكي"), ("EGP", "جنيه مصري")], max_length=3, verbose_name="العملة")),
                ("amount_words", models.CharField(blank=True, max_length=300, verbose_name="المبلغ بالحروف")),
                ("source_row", models.PositiveIntegerField(blank=True, null=True, verbose_name="رقم الصف في Excel")),
                ("source_data", models.JSONField(blank=True, default=dict, verbose_name="بيانات الصف الأصلية")),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lines", to="students.supplyorder")),
                ("student", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="supply_order_lines", to="students.student")),
            ],
            options={"verbose_name": "بند أمر توريد", "verbose_name_plural": "بنود أوامر التوريد", "ordering": ["id"]},
        ),
    ]
