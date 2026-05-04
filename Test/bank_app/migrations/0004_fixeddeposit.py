# Generated migration for FixedDeposit model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bank_app', '0003_alter_auditlog_action_crewaireasoninglog'),
    ]

    operations = [
        migrations.CreateModel(
            name='FixedDeposit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fd_id', models.CharField(editable=False, max_length=50, unique=True)),
                ('account_number', models.CharField(blank=True, max_length=50, null=True)),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('ACTIVE', 'Active'), ('MATURED', 'Matured'), ('CLOSED', 'Closed'), ('PREMATURELY_CLOSED', 'Prematurely Closed')], default='PENDING', max_length=20)),
                ('region', models.CharField(choices=[('IN', 'India'), ('US', 'United States')], default='IN', max_length=2)),
                ('user_session_id', models.CharField(blank=True, max_length=100, null=True)),
                ('customer_name', models.CharField(blank=True, max_length=200, null=True)),
                ('customer_email', models.EmailField(blank=True, max_length=254, null=True)),
                ('customer_phone', models.CharField(blank=True, max_length=20, null=True)),
                ('bank_name', models.CharField(max_length=200)),
                ('rate', models.DecimalField(decimal_places=2, max_digits=5)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=15)),
                ('tenure_months', models.IntegerField()),
                ('start_date', models.DateField()),
                ('maturity_date', models.DateField()),
                ('maturity_amount', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('interest_earned', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('senior_citizen', models.BooleanField(default=False)),
                ('loan_against_fd', models.BooleanField(default=False)),
                ('auto_renewal', models.BooleanField(default=False)),
                ('certificate_path', models.CharField(blank=True, max_length=500, null=True)),
                ('certificate_generated', models.BooleanField(default=False)),
                ('email_sent', models.BooleanField(default=False)),
                ('email_sent_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('confirmed_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='fixeddeposit',
            index=models.Index(fields=['status', 'created_at'], name='bank_app_fi_status_...'),
        ),
        migrations.AddIndex(
            model_name='fixeddeposit',
            index=models.Index(fields=['fd_id'], name='bank_app_fi_fd_id_...'),
        ),
        migrations.AddIndex(
            model_name='fixeddeposit',
            index=models.Index(fields=['customer_email'], name='bank_app_fi_custome_...'),
        ),
    ]
