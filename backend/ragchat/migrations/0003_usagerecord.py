from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ragchat", "0002_document_session_and_chunks"),
    ]

    operations = [
        migrations.CreateModel(
            name="UsageRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("client_id", models.CharField(db_index=True, max_length=64)),
                (
                    "kind",
                    models.CharField(choices=[("question", "Question"), ("upload", "Upload")], max_length=16),
                ),
                ("cost_usd", models.FloatField(default=0.0)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
