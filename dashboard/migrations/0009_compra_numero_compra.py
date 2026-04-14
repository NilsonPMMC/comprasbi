from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0008_synccheckpoint"),
    ]

    operations = [
        migrations.AddField(
            model_name="compra",
            name="numero_compra",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
    ]

