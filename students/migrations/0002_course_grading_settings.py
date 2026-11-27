from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("students", "0001_initial")]
    operations = [
        migrations.AddField(model_name="course", name="max_score", field=models.DecimalField(decimal_places=2, default=100, max_digits=6, verbose_name="النهاية العظمى")),
        migrations.AddField(model_name="course", name="pass_score", field=models.DecimalField(decimal_places=2, default=50, max_digits=6, verbose_name="درجة النجاح")),
        migrations.AddField(model_name="course", name="excellent_percent", field=models.DecimalField(decimal_places=2, default=85, max_digits=5, verbose_name="حد الامتياز %")),
        migrations.AddField(model_name="course", name="very_good_percent", field=models.DecimalField(decimal_places=2, default=75, max_digits=5, verbose_name="حد جيد جدًا %")),
        migrations.AddField(model_name="course", name="good_percent", field=models.DecimalField(decimal_places=2, default=65, max_digits=5, verbose_name="حد جيد %")),
    ]
