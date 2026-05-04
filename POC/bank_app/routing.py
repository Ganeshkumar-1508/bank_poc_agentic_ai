"""
WebSocket routing for bank_app
"""

from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path('ws/dashboard/', consumers.DashboardConsumer.as_view()),
]
