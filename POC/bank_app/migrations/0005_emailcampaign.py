# Generated migration for EmailCampaign and EmailCampaignLog models

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('bank_app', '0004_fixeddeposit'),
    ]

    operations = [
        migrations.CreateModel(
            name='EmailCampaign',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('subject', models.CharField(max_length=300)),
                ('template_type', models.CharField(choices=[('FD_CONFIRMATION', 'FD Confirmation'), ('FD_MATURITY_REMINDER', 'FD Maturity Reminder'), ('FD_RENEWAL_OFFER', 'FD Renewal Offer'), ('CUSTOM', 'Custom Template')], max_length=50)),
                ('template_content', models.TextField(blank=True, null=True)),
                ('target_filters', models.JSONField(blank=True, default=dict)),
                ('status', models.CharField(choices=[('DRAFT', 'Draft'), ('SCHEDULED', 'Scheduled'), ('SENDING', 'Sending'), ('COMPLETED', 'Completed'), ('FAILED', 'Failed'), ('PAUSED', 'Paused')], default='DRAFT', max_length=20)),
                ('total_recipients', models.IntegerField(default=0)),
                ('total_sent', models.IntegerField(default=0)),
                ('total_delivered', models.IntegerField(default=0)),
                ('total_opened', models.IntegerField(default=0)),
                ('total_failed', models.IntegerField(default=0)),
                ('created_by', models.CharField(default='ADMIN', max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('scheduled_at', models.DateTimeField(blank=True, null=True)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('sender_email', models.EmailField(default='noreply@bankpoc.com', max_length=254)),
                ('sender_name', models.CharField(default='Bank POC', max_length=200)),
                ('reply_to_email', models.EmailField(blank=True, max_length=254, null=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='EmailCampaignLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('recipient_email', models.EmailField(max_length=254)),
                ('recipient_name', models.CharField(blank=True, max_length=200, null=True)),
                ('subject', models.CharField(max_length=300)),
                ('content', models.TextField()),
                ('delivery_status', models.CharField(choices=[('PENDING', 'Pending'), ('SENT', 'Sent'), ('DELIVERED', 'Delivered'), ('OPENED', 'Opened'), ('CLICKED', 'Clicked'), ('BOUNCED', 'Bounced'), ('FAILED', 'Failed')], default='PENDING', max_length=20)),
                ('failure_reason', models.TextField(blank=True, null=True)),
                ('queued_at', models.DateTimeField(auto_now_add=True)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('delivered_at', models.DateTimeField(blank=True, null=True)),
                ('opened_at', models.DateTimeField(blank=True, null=True)),
                ('clicked_at', models.DateTimeField(blank=True, null=True)),
                ('tracking_token', models.CharField(editable=False, max_length=100, unique=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.TextField(blank=True, null=True)),
                ('campaign', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='logs', to='bank_app.emailcampaign')),
            ],
            options={
                'ordering': ['-queued_at'],
            },
        ),
        migrations.AddIndex(
            model_name='emailcampaign',
            index=models.Index(fields=['status', 'created_at'], name='bank_app_em_status_8f8a0e_idx'),
        ),
        migrations.AddIndex(
            model_name='emailcampaign',
            index=models.Index(fields=['template_type'], name='bank_app_em_template_2c5d1a_idx'),
        ),
        migrations.AddIndex(
            model_name='emailcampaignlog',
            index=models.Index(fields=['campaign', 'delivery_status'], name='bank_app_em_campaign_4e7b2c_idx'),
        ),
        migrations.AddIndex(
            model_name='emailcampaignlog',
            index=models.Index(fields=['recipient_email'], name='bank_app_em_recipie_8a3f1d_idx'),
        ),
        migrations.AddIndex(
            model_name='emailcampaignlog',
            index=models.Index(fields=['tracking_token'], name='bank_app_em_tracki_9b4e2f_idx'),
        ),
    ]
