"""
Admin Panel URL Configuration
"""
from django.urls import path
from . import admin_views

app_name = 'admin_panel'

urlpatterns = [
    # Authentication
    path('login/', admin_views.admin_login, name='admin_login'),
    path('logout/', admin_views.admin_logout, name='admin_logout'),
    
    # Dashboard
    path('', admin_views.admin_dashboard, name='admin_dashboard'),
    
    # User Management
    path('users/', admin_views.admin_user_list, name='admin_user_list'),
    path('users/<str:session_id>/', admin_views.admin_user_detail, name='admin_user_detail'),
    path('users/<str:session_id>/toggle/', admin_views.admin_toggle_user_active, name='admin_toggle_user_active'),
    
    # Transaction Monitoring
    path('transactions/', admin_views.admin_transaction_list, name='admin_transaction_list'),
    path('transactions/<str:application_id>/', admin_views.admin_transaction_detail, name='admin_transaction_detail'),
    path('transactions/<str:application_id>/approve/', admin_views.admin_approve_transaction, name='admin_approve_transaction'),
    path('transactions/<str:application_id>/reject/', admin_views.admin_reject_transaction, name='admin_reject_transaction'),
    
    # Analytics
    path('analytics/', admin_views.admin_analytics, name='admin_analytics'),
    
    # Configuration
    path('config/', admin_views.admin_config, name='admin_config'),
    path('config/update/', admin_views.admin_update_config, name='admin_update_config'),
    
    # Audit Trail
    path('audit-log/', admin_views.admin_audit_log, name='admin_audit_log'),
    
    # Crew AI Logs
    path('crew-logs/', admin_views.admin_crew_logs, name='admin_crew_logs'),
    
    # Content Management
    path('content/', admin_views.admin_content, name='admin_content'),
    path('content/fd-rates/<int:rate_id>/', admin_views.admin_update_fd_rate, name='admin_update_fd_rate'),
    path('content/fd-rates/add/', admin_views.admin_add_fd_rate, name='admin_add_fd_rate'),
    
    # Email Campaign Management
    path('email-campaigns/', admin_views.admin_email_campaigns, name='admin_email_campaigns'),
    path('email-campaigns/create/', admin_views.admin_create_campaign, name='admin_create_campaign'),
    path('email-campaigns/<int:campaign_id>/', admin_views.admin_get_campaign, name='admin_get_campaign'),
    path('email-campaigns/<int:campaign_id>/update/', admin_views.admin_update_campaign, name='admin_update_campaign'),
    
    # Database Query Interface (Admin-Only)
    path('database-query/', admin_views.admin_database_query, name='admin_database_query'),
    path('database-query/api/', admin_views.admin_database_query_api, name='admin_database_query_api'),
    path('database-query/history/', admin_views.admin_query_history, name='admin_query_history'),
    path('database-query/audit/', admin_views.admin_query_audit_log, name='admin_query_audit_log'),
    path('email-campaigns/<int:campaign_id>/send/', admin_views.admin_send_campaign, name='admin_send_campaign'),
    path('email-campaigns/<int:campaign_id>/pause/', admin_views.admin_pause_campaign, name='admin_pause_campaign'),
    path('email-campaigns/<int:campaign_id>/preview/', admin_views.admin_preview_template, name='admin_preview_template'),
    path('email-campaigns/<int:campaign_id>/stats/', admin_views.admin_get_campaign_stats, name='admin_get_campaign_stats'),
    path('email-campaigns/<int:campaign_id>/logs/', admin_views.admin_campaign_logs, name='admin_campaign_logs'),
    path('email-campaigns/generate-template/', admin_views.admin_generate_template, name='admin_generate_template'),
    
    # Model Management (CRUD for all database models)
    path('models/', admin_views.admin_model_management, name='admin_model_management'),
    path('models/<str:model_name>/', admin_views.admin_model_list, name='admin_model_list'),
    path('models/<str:model_name>/<int:record_id>/', admin_views.admin_model_detail, name='admin_model_detail'),
    path('models/<str:model_name>/create/', admin_views.admin_model_create, name='admin_model_create'),
    path('models/<str:model_name>/<int:record_id>/update/', admin_views.admin_model_update, name='admin_model_update'),
    path('models/<str:model_name>/<int:record_id>/delete/', admin_views.admin_model_delete, name='admin_model_delete'),
]
