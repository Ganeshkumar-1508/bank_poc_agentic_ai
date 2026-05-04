"""
Smart Assistant Views.
Contains endpoints for the AI-powered chat assistant.

Simplified version: Uses the new generic run_crew endpoint.
"""

import json
import logging
import traceback

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from .base import (
    logger,
    get_user_region_from_session,
)
from .crew_api_views import run_crew

logger = logging.getLogger(__name__)


def format_crew_response(result_dict, success=True):
    """Format CrewAI response for JSON serialization."""
    from datetime import datetime
    return {
        'success': success,
        'timestamp': datetime.now().isoformat(),
        **result_dict
    }


# =============================================================================
# SMART ASSISTANT QUERY API
# =============================================================================

@csrf_exempt
@require_POST
def smart_assistant_query(request):
    """
    Smart Assistant Query API

    API endpoint for the smart assistant chat interface.
    Routes the query through Router Crew for intent classification
    and returns the appropriate response.

    POST /api/smart-assistant-query/
    Body: {
        "query": "What are the best FD rates?",
        "session_id": "optional-session-id" (optional)
    }
    """
    try:
        data = json.loads(request.body)
        user_query = data.get('query', '')
        session_id = data.get('session_id', request.session.session_key or 'anonymous')

        if not user_query:
            return JsonResponse({'error': 'Query is required'}, status=400)

        # Get user region
        region_data = get_user_region_from_session(request)
        region = region_data.get('country_name', 'India')

        logger.info(f"Smart Assistant query: {user_query[:50]}... (session: {session_id})")

        # Call the generic run_crew endpoint with router crew type
        # Simulate the request that would be made from the frontend
        class MockRequest:
            def __init__(self, data):
                self.body = json.dumps(data).encode()
                self.META = request.META

        mock_request = MockRequest({
            'crew_type': 'router',
            'query': user_query,
            'region': region
        })

        response = run_crew(mock_request)
        response_data = json.loads(response.content)

        # Extract intent from user query (simple keyword matching)
        intent = "UNKNOWN"
        intent_mapping = {
            "CREDIT_RISK": ["credit", "loan approval", "credit score", "loan odds"],
            "LOAN_CREATION": ["apply for loan", "loan application", "get a loan"],
            "MORTGAGE_ANALYTICS": ["mortgage", "home loan"],
            "FD_TEMPLATE": ["fd rates", "fixed deposit", "fd comparison"],
            "ANALYSIS": ["analyze", "analysis", "data"],
            "RESEARCH": ["research", "news", "market"],
            "DATABASE": ["database", "sql", "query data"],
            "VISUALIZATION": ["chart", "graph", "visualize"],
            "ONBOARDING": ["onboard", "kyc", "new account"],
        }

        query_lower = user_query.lower()
        for intent_name, keywords in intent_mapping.items():
            if any(keyword in query_lower for keyword in keywords):
                intent = intent_name
                break

        # Log the interaction (optional - may fail if models not available)
        try:
            from .models import CrewAIReasoningLog
            CrewAIReasoningLog.objects.create(
                session_id=session_id,
                crew_type='smart_assistant',
                task_description=f'Smart Assistant query: {user_query[:100]}',
                agent_name='router_agent',
                reasoning=f'Intent: {intent}',
                output=response_data.get('result', '')[:5000],
                execution_time=0
            )
        except Exception as log_error:
            logger.warning(f"Failed to log smart assistant interaction: {log_error}")
        
        return JsonResponse(format_crew_response({
            'query': user_query,
            'session_id': session_id,
            'region': region,
            'intent': intent,
            'result': response_data.get('result', ''),
            'crew_type': 'smart_assistant'
        }))
    
    except ImportError as e:
        logger.error(f"Smart Assistant import error: {e}")
        return JsonResponse({'error': f'CrewAI functions not available: {str(e)}'}, status=503)
    except Exception as e:
        logger.error(f"Smart Assistant error: {e}")
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)
