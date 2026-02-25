import requests
from crewai.tools import tool

@tool("OpenSanctions Search")
def search_sanctions(query: str) -> str:
    """
    Search the OpenSanctions database for entities matching the query.
    Use this to check if a user (Name or PAN) appears on sanctions lists.
    """
    try:
        url = "https://api.opensanctions.org/search/default"
        params = {
            "q": query,
            "limit": 5,
            "schema": "Person" 
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        results = data.get("results", [])
        
        if not results:
            return f"No match found for '{query}' on OpenSanctions. User is clear."
        
        summary = f"Found {len(results)} potential match(es) for '{query}':\n"
        for item in results:
            name = item.get("properties", {}).get("name", ["Unknown"])[0]
            schema = item.get("schema", "Unknown")
            summary += f"- Match: {name} (Type: {schema})\n"
            
        return f"WARNING: {summary}"

    except Exception as e:
        return f"Error searching OpenSanctions: {str(e)}"