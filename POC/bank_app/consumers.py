"""
WebSocket Consumers for real-time dashboard updates
"""

import json
from channels.generic.websocket import AsyncWebsocketConsumer


class DashboardConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for dashboard real-time updates.
    
    Handles:
    - Loan status changes
    - Admin actions (bulk operations)
    - CrewAI decisions
    """

    async def connect(self):
        """Handle WebSocket connection."""
        self.group_name = 'dashboard_updates'
        
        # Join group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Send welcome message
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected to dashboard updates'
        }))

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        # Leave group
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def loan_status_update(self, event):
        """
        Send loan status update to connected clients.
        
        Event format:
        {
            'type': 'loan_status_update',
            'loan_id': int,
            'application_id': str,
            'old_status': str,
            'new_status': str,
            'timestamp': str
        }
        """
        await self.send(text_data=json.dumps({
            'type': 'loan_status_update',
            'loan_id': event['loan_id'],
            'application_id': event.get('application_id'),
            'old_status': event['old_status'],
            'new_status': event['new_status'],
            'timestamp': event['timestamp']
        }))

    async def admin_action(self, event):
        """
        Send admin action notification to connected clients.
        
        Event format:
        {
            'type': 'admin_action',
            'action': str,
            'affected_loans': list,
            'timestamp': str
        }
        """
        await self.send(text_data=json.dumps({
            'type': 'admin_action',
            'action': event['action'],
            'affected_loans': event['affected_loans'],
            'timestamp': event['timestamp']
        }))

    async def crewai_decision(self, event):
        """
        Send CrewAI decision notification to connected clients.
        
        Event format:
        {
            'type': 'crewai_decision',
            'loan_id': int,
            'decision': str,
            'confidence': float,
            'reasoning': dict
        }
        """
        await self.send(text_data=json.dumps({
            'type': 'crewai_decision',
            'loan_id': event['loan_id'],
            'decision': event['decision'],
            'confidence': event['confidence'],
            'reasoning': event.get('reasoning', {})
        }))
