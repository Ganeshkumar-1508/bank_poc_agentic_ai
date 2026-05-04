"""
Financial News API Views.
Contains endpoints for fetching financial news and country data.
"""

import os
import json
import logging
import requests as news_requests

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from .base import logger, fetch_country_data

logger = logging.getLogger(__name__)


# =============================================================================
# COUNTRIES API
# =============================================================================

@csrf_exempt
def countries_api(request):
    """
    Countries API endpoint - Returns list of available countries for financial news.
    
    GET /api/countries/
    Returns: {
        "countries": [
            {"code": "US", "name": "United States", "ddg_region": "us-en"},
            {"code": "IN", "name": "India", "ddg_region": "in-en"},
            ...
        ]
    }
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        # Fetch country data from config
        country_data = fetch_country_data()
        
        # Format for frontend consumption with all fields
        countries = []
        for code, data in country_data.items():
            countries.append({
                'code': code,
                'name': data.get('name', code),
                'official_name': data.get('official_name', data.get('name', code)),
                'alpha_3': data.get('alpha_3', ''),
                'currency_code': data.get('currency_code', ''),
                'currency_symbol': data.get('currency_symbol', ''),
                'ddg_region': data.get('ddg_region', '')
            })
        
        # Sort by name
        countries.sort(key=lambda x: x['name'])
        
        return JsonResponse({'countries': countries})
    
    except Exception as e:
        logger.error(f"Countries API error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# FINANCIAL NEWS API
# =============================================================================

@csrf_exempt
@require_POST
def financial_news_api(request):
    """
    Financial news API endpoint - Uses NewsData.io for real financial news.
    
    POST /api/financial-news/
    Body: {
        "query": "federal reserve" (optional search query),
        "country": "in" (optional, default: "us"),
        "category": "banking" (optional: banking, markets, crypto, economy, regulation),
        "days": 7 (optional: 7, 30, 90 for date range)
    }
    """
    try:
        data = json.loads(request.body)
        
        # Get API key from environment
        newsdata_api_key = os.getenv('NEWSDATA_API_KEY', '')
        if not newsdata_api_key:
            return JsonResponse({
                'error': 'NEWSDATA_API_KEY not configured. Please add it to your .env file.'
            }, status=500)
        
        # Get parameters
        query = data.get('query', '')
        country = data.get('country', 'us')  # Default to US
        category = data.get('category', 'all')
        days = int(data.get('days', 7))
        
        # Build the API URL and parameters
        # Using /market endpoint for financial/business news
        url = "https://newsdata.io/api/1/market"
        params = {
            'apikey': newsdata_api_key,
            'language': 'en',
            'removeduplicate': 1,
        }
        
        # Add country if specified
        if country and country != 'all':
            params['country'] = country.lower()
        
        # Add query if provided
        if query:
            params['q'] = query
        
        # Add category filtering via domain/topic
        category_domains = {
            'banking': 'reuters.com,bloomberg.com,wsj.com,ft.com',
            'markets': 'marketwatch.com,investing.com,seekingalpha.com',
            'crypto': 'coindesk.com,cointelegraph.com',
            'economy': 'economictimes.indiatimes.com,blomberg.com/economy',
            'regulation': 'reuters.com/legal,ft.com/regulation'
        }
        if category and category != 'all' and category in category_domains:
            params['domain'] = category_domains[category]
        
        # Make the API request
        response = news_requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        news_data = response.json()
        
        if news_data.get('status') != 'success':
            return JsonResponse({
                'error': 'Failed to fetch news from NewsData.io',
                'message': news_data.get('description', 'Unknown error')
            }, status=500)
        
        # Process and format the articles
        articles = news_data.get('results', [])
        formatted_news = []
        
        for article in articles:
            formatted_news.append({
                'title': article.get('title', 'Untitled'),
                'description': article.get('description', ''),
                'source': article.get('source_name') or article.get('source_id', 'Unknown'),
                'published_at': article.get('pubDate', ''),
                'url': article.get('link', ''),
                'image_url': article.get('image_url', ''),
                'category': ', '.join(article.get('category', [])) or 'General',
                'content': article.get('content', '')[:500] if article.get('content') else ''
            })
        
        return JsonResponse({
            'status': 'success',
            'news': formatted_news,
            'total_results': news_data.get('totalResults', len(formatted_news)),
            'country': country,
            'category': category
        })
    
    except ImportError:
        return JsonResponse({'error': 'requests library not installed'}, status=500)
    except Exception as e:
        logger.error(f"Financial news API error: {e}")
        return JsonResponse({'error': str(e)}, status=500)
