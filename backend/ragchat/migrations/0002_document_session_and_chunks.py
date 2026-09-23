from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ragchat", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="session_id",
            field=models.CharField(db_index=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="document",
            name="chunk_count",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
