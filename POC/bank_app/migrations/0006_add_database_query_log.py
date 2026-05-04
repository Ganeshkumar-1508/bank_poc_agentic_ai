# Generated migration for DatabaseQueryLog model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bank_app', '0005_emailcampaign'),
    ]

    operations = [
        migrations.CreateModel(
            name='DatabaseQueryLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('query_text', models.TextField(help_text="Natural language query from user")),
                ('sql_generated', models.TextField(blank=True, help_text="Generated SQL query", null=True)),
                ('result_summary', models.JSONField(blank=True, help_text="Summary of query results", null=True)),
                ('result_count', models.IntegerField(default=0, help_text="Number of rows returned")),
                ('row_limit_applied', models.IntegerField(default=1000, help_text="Max rows allowed")),
                ('executed_by', models.CharField(default='ADMIN', help_text="Admin username", max_length=100)),
                ('executed_at', models.DateTimeField(auto_now_add=True)),
                ('execution_time_ms', models.IntegerField(blank=True, help_text="Query execution time in ms", null=True)),
                ('status', models.CharField(choices=[('SUCCESS', 'Success'), ('ERROR', 'Error'), ('TIMEOUT', 'Timeout'), ('BLOCKED', 'Blocked - Safety Check Failed')], default='SUCCESS', max_length=20)),
                ('error_message', models.TextField(blank=True, null=True)),
                ('is_read_only', models.BooleanField(default=True, help_text="Was this a read-only query?")),
                ('sensitive_data_masked', models.BooleanField(default=False, help_text="Was sensitive data masked?")),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('exported_as', models.CharField(blank=True, help_text="CSV, JSON, or empty", max_length=10, null=True)),
            ],
            options={
                'ordering': ['-executed_at'],
            },
        ),
        migrations.AddIndex(
            model_name='databasequerylog',
            index=models.Index(fields=['status', 'executed_at'], name='bank_app_da_status_exec_idx'),
        ),
        migrations.AddIndex(
            model_name='databasequerylog',
            index=models.Index(fields=['executed_by', 'executed_at'], name='bank_app_da_execute_exec_idx'),
        ),
        migrations.AddIndex(
            model_name='databasequerylog',
            index=models.Index(fields=['is_read_only', 'executed_at'], name='bank_app_da_is_read_exec_idx'),
        ),
    ]
