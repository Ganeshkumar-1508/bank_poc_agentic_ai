# Bank POC Agentic AI - Simplification Plan

## Executive Summary

This document provides a detailed plan to simplify the `bank_poc_agentic_ai_new_UI` project by reducing complexity in the Agent outputs ↔ UI ↔ user interactions flow. The current architecture has multiple redundant layers that can be consolidated into a simpler, more direct pattern.

---

## 1. Current Architecture Analysis

### 1.1 File Count Involved in Single User Interaction

A typical user interaction (e.g., Smart Assistant query) flows through:

```
User Input (HTML) 
  → main.js (fetch call)
  → smart_assistant_views.py (Django view)
  → base.py (lazy loader)
  → crews.py (wrapper)
  → crew_factory.py (factory pattern)
  → agents.py (agent definitions)
  → tasks.py (task definitions)
  → CrewAI execution
  → Back through same chain
  → markdown_renderer.js (client-side rendering)
  → UI Display
```

**Files involved: 8-10 files per interaction**

### 1.2 Current Complexity Map

#### Agent → Crew → API → UI Paths

| Path Type | Files | Lines (approx) | Complexity |
|-----------|-------|----------------|------------|
| **CrewFactory** | [`crew_factory.py`](Test/crew_factory.py) | 816 lines | High - Factory pattern with 11 crew types |
| **Crew Wrappers** | [`crews.py`](Test/crews.py) | 561 lines | Medium - Backward compatibility wrappers |
| **Base Lazy Loading** | [`base.py`](Test/bank_app/views/base.py) | 778 lines | High - Lazy import pattern with 20+ wrapper functions |
| **API Views** | [`crew_api_views.py`](Test/bank_app/views/crew_api_views.py) | 891 lines | High - 11 separate endpoint handlers |
| **Agent Definitions** | [`agents.py`](Test/agents.py) | 1041 lines | Medium - 10 agent creation functions |
| **Task Definitions** | [`tasks.py`](Test/tasks.py) | 1010 lines | Medium - 10 task creation functions |
| **Markdown Renderer** | [`markdown_renderer.js`](Test/bank_app/static/js/markdown_renderer.js) | 465 lines | Medium - Multiple rendering approaches |
| **Smart Assistant** | [`smart_assistant_views.py`](Test/bank_app/views/smart_assistant_views.py) | 120 lines | Low - Simple wrapper |

**Total: ~5,682 lines across 8 core files**

### 1.3 Redundant Layers Identified

1. **CrewFactory Pattern** ([`crew_factory.py`](Test/crew_factory.py:32))
   - `CrewType` enum with 11 crew types
   - `CrewFactory` class with 20+ static methods
   - Generic `create_crew()` and `run_crew()` methods
   - **Issue**: Over-engineered for a POC; direct function calls would suffice

2. **Lazy Loading in base.py** ([`base.py`](Test/bank_app/views/base.py:89))
   - `_crew_functions_loaded` state tracking
   - `_get_crew_functions()` lazy loader
   - 20+ wrapper functions (e.g., [`create_td_fd_agents()`](Test/bank_app/views/base.py:216), [`run_analysis_crew()`](Test/bank_app/views/base.py:300))
   - **Issue**: Adds indirection without real benefit; causes circular import complexity

3. **Crews.py Wrappers** ([`crews.py`](Test/crews.py:29))
   - Functions like [`run_router_crew()`](Test/crews.py:29) that just delegate to CrewFactory
   - **Issue**: Double indirection (base.py → crews.py → crew_factory.py)

4. **Multiple API Endpoints** ([`crew_api_views.py`](Test/bank_app/views/crew_api_views.py:56))
   - 11 separate endpoint functions (e.g., [`fd_advisor_crew_api()`](Test/bank_app/views/crew_api_views.py:58), [`credit_risk_crew_api()`](Test/bank_app/views/crew_api_views.py:119))
   - Each duplicates similar error handling and response formatting
   - **Issue**: Can be consolidated into 1-2 generic endpoints

5. **Multiple Markdown Renderers** ([`markdown_renderer.js`](Test/bank_app/static/js/markdown_renderer.js:99))
   - [`renderMarkdown()`](Test/bank_app/static/js/markdown_renderer.js:99) with multiple options
   - [`parseCrewAISpecialFormatting()`](Test/bank_app/static/js/markdown_renderer.js:151) for CrewAI-specific formatting
   - [`simpleMarkdownToHtml()`](Test/bank_app/static/js/markdown_renderer.js:226) fallback
   - **Issue**: marked.js CDN alone would suffice for most cases

---

## 2. Simplification Strategy: Option A (Recommended)

### Option A: Consolidate to Single Pattern

**Philosophy**: Keep all crew types but simplify the execution path by removing indirection layers.

#### 2.1 New Simplified Flow

```
User Input (HTML)
  ↓
JavaScript: fetch('/api/run-crew/', { crew_type: 'analysis', query: '...' })
  ↓
Django view: Single generic endpoint
  ↓
View imports crew function directly (no lazy loading)
  ↓
crew.kickoff()
  ↓
Return JSON: { result: output.raw }
  ↓
JavaScript: document.getElementById('result').innerHTML = marked.parse(data.result)
  ↓
UI Display
```

#### 2.2 Changes by File

##### DELETE These Files (or significantly reduce):

| File | Action | Reason |
|------|--------|--------|
| [`Test/crew_factory.py`](Test/crew_factory.py) | **DELETE** | Factory pattern unnecessary; direct imports work |
| [`Test/bank_app/views/base.py`](Test/bank_app/views/base.py) | **REPLACE** | Remove lazy loading; keep only helper functions |
| [`Test/crews.py`](Test/crews.py) | **DELETE** | Wrapper layer redundant after removing CrewFactory |

##### SIMPLIFY These Files:

| File | Current Lines | Target Lines | Changes |
|------|---------------|--------------|---------|
| [`Test/bank_app/views/crew_api_views.py`](Test/bank_app/views/crew_api_views.py) | 891 | ~200 | Consolidate 11 endpoints into 1 generic `/api/run-crew/` endpoint |
| [`Test/bank_app/static/js/markdown_renderer.js`](Test/bank_app/static/js/markdown_renderer.js) | 465 | ~100 | Use marked.js CDN directly; remove CrewAI-specific parsing |
| [`Test/bank_app/views/smart_assistant_views.py`](Test/bank_app/views/smart_assistant_views.py) | 120 | ~60 | Simplify to use generic crew runner |

##### KEEP These Files (minimal changes):

| File | Reason |
|------|--------|
| [`Test/agents.py`](Test/agents.py) | Core agent definitions; keep as-is |
| [`Test/tasks.py`](Test/tasks.py) | Core task definitions; keep as-is |
| [`Test/bank_app/static/js/main.js`](Test/bank_app/static/js/main.js) | UI logic; keep as-is |
| HTML templates | UI structure; keep as-is |

---

## 3. What to Remove vs Keep

### 3.1 Files to DELETE

1. **[`Test/crew_factory.py`](Test/crew_factory.py)** (816 lines)
   - Entire factory pattern is over-engineering
   - Replace with direct function calls from [`agents.py`](Test/agents.py) and [`tasks.py`](Test/tasks.py)

2. **[`Test/crews.py`](Test/crews.py)** (561 lines)
   - All wrapper functions just delegate to CrewFactory
   - After removing CrewFactory, this file serves no purpose

3. **Lazy loading code in [`base.py`](Test/bank_app/views/base.py:89)** (~400 lines)
   - Remove `_crew_functions_loaded`, `_get_crew_functions()`
   - Remove 20+ wrapper functions (lines 216-392)
   - Keep only: logging setup, EMI calculator functions, geolocation helpers

### 3.2 Code to SIMPLIFY

#### 3.2.1 New Generic API Endpoint

**Replace** 11 endpoints in [`crew_api_views.py`](Test/bank_app/views/crew_api_views.py) with:

```python
# NEW: Simplified crew_api_views.py (replaces entire file)
import json
import logging
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

# Direct imports - no lazy loading
from agents import (
    create_router_agents, create_analysis_agents, create_research_agents,
    create_database_agents, create_visualization_agents, create_credit_risk_agents,
    create_loan_creation_agents, create_mortgage_agents, create_aml_agents,
    create_td_fd_agents, create_fd_template_agents
)
from tasks import (
    create_routing_task, create_analysis_tasks, create_research_tasks,
    create_database_tasks, create_visualization_task, create_credit_risk_tasks,
    create_loan_creation_tasks, create_mortgage_analytics_tasks,
    create_aml_execution_tasks, create_td_fd_tasks, create_fd_template_tasks
)
from crewai import Crew, Process

CREW_FUNCTION_MAP = {
    'router': (create_router_agents, lambda agents, q, r: [create_routing_task(agents, q, r)]),
    'analysis': (create_analysis_agents, lambda agents, q, r: create_analysis_tasks(agents, q, r)),
    'research': (create_research_agents, lambda agents, q, r: create_research_tasks(agents, q, r)),
    'database': (create_database_agents, lambda agents, q, r: create_database_tasks(agents, q)),
    'visualization': (create_visualization_agents, lambda agents, q, r: [create_visualization_task(agents, q, r)]),
    'credit_risk': (create_credit_risk_agents, lambda agents, q, r: create_credit_risk_tasks(agents, q)),
    'loan_creation': (create_loan_creation_agents, lambda agents, q, r: create_loan_creation_tasks(agents, q)),
    'mortgage_analytics': (create_mortgage_agents, lambda agents, q, r: create_mortgage_analytics_tasks(agents, q)),
    'aml': (create_aml_agents, lambda agents, q, r: create_aml_execution_tasks(agents, q)),
    'fd_advisor': (create_td_fd_agents, lambda agents, q, r: create_td_fd_tasks(agents, q)),
    'fd_template': (create_fd_template_agents, lambda agents, q, r: create_fd_template_tasks(agents, q)),
}

@csrf_exempt
@require_POST
def run_crew(request):
    """
    Generic CrewAI execution endpoint.
    
    POST /api/run-crew/
    Body: {
        "crew_type": "analysis",
        "query": "What are the best FD rates?",
        "region": "India" (optional),
        "additional_params": {} (optional)
    }
    """
    try:
        data = json.loads(request.body)
        crew_type = data.get('crew_type', '').lower()
        query = data.get('query', '')
        region = data.get('region', 'India')
        
        if crew_type not in CREW_FUNCTION_MAP:
            return JsonResponse({'error': f'Unknown crew_type: {crew_type}'}, status=400)
        if not query:
            return JsonResponse({'error': 'query is required'}, status=400)
        
        # Get agent and task creators
        agent_creator, task_creator = CREW_FUNCTION_MAP[crew_type]
        
        # Create agents and tasks
        agents = agent_creator(region=region) if region else agent_creator()
        tasks = task_creator(agents, query, region)
        
        # Ensure tasks is a list
        if not isinstance(tasks, list):
            tasks = [tasks]
        
        # Create and run crew
        crew = Crew(
            agents=list(agents.values()) if isinstance(agents, dict) else agents,
            tasks=tasks,
            process=Process.sequential,
            verbose=False
        )
        output = crew.kickoff()
        
        # Return simple response
        return JsonResponse({
            'result': output.raw if hasattr(output, 'raw') else str(output),
            'crew_type': crew_type
        })
        
    except Exception as e:
        logger.error(f"Crew execution error: {e}")
        return JsonResponse({'error': str(e)}, status=500)
```

#### 3.2.2 Simplified JavaScript

**Replace** [`markdown_renderer.js`](Test/bank_app/static/js/markdown_renderer.js) with:

```javascript
// NEW: Simple markdown renderer (replaces markdown_renderer.js)
(function(global) {
    'use strict';
    
    let marked = null;
    
    function loadMarked() {
        return new Promise((resolve, reject) => {
            if (typeof marked !== 'undefined') {
                resolve(marked);
                return;
            }
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/marked/marked.min.js';
            script.onload = () => { marked = window.marked; resolve(marked); };
            script.onerror = () => reject(new Error('Failed to load marked.js'));
            document.head.appendChild(script);
        });
    }
    
    async function renderMarkdown(markdown) {
        if (!marked) await loadMarked();
        return marked ? marked.parse(markdown) : markdown;
    }
    
    global.renderMarkdown = renderMarkdown;
    
})(window);
```

**Usage in HTML/JS:**
```javascript
// Before: Complex rendering
const parsed = parseCrewAIOutput(rawOutput);
displayCrewAIResult(parsed);

// After: Simple rendering
const html = await renderMarkdown(rawOutput);
document.getElementById('result').innerHTML = html;
```

#### 3.2.3 Simplified base.py

**Keep only** these sections in [`base.py`](Test/bank_app/views/base.py):
- Lines 1-88: Imports, logging, path configuration
- Lines 550-778: EMI calculator functions (keep as-is)
- Lines 490-548: Geolocation helper functions (keep as-is)

**Delete**: Lines 89-489 (lazy loading infrastructure)

---

## 4. Simplified Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         SIMPLIFIED ARCHITECTURE                      │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────┐
│   User HTML  │
│  Templates   │
└──────┬───────┘
       │
       │ User clicks button / sends query
       ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    JavaScript (main.js)                              │
│  fetch('/api/run-crew/', { crew_type: 'analysis', query: '...' })  │
└──────┬──────────────────────────────────────────────────────────────┘
       │
       │ HTTP POST
       ↓
┌─────────────────────────────────────────────────────────────────────┐
│              crew_api_views.py (SINGLE ENDPOINT)                     │
│  run_crew(request)                                                   │
│    1. Parse crew_type from request                                   │
│    2. Import agent_creator, task_creator directly                    │
│    3. agents = agent_creator(region)                                 │
│    4. tasks = task_creator(agents, query, region)                    │
│    5. crew = Crew(agents=agents, tasks=tasks)                        │
│    6. output = crew.kickoff()                                        │
│    7. return JsonResponse({result: output.raw})                      │
└──────┬──────────────────────────────────────────────────────────────┘
       │
       │ Direct import (no lazy loading)
       ↓
┌──────────────────────┐     ┌──────────────────────┐
│    agents.py         │     │     tasks.py         │
│  create_analysis_    │     │  create_analysis_    │
│  agents()            │     │  tasks()             │
└──────────────────────┘     └──────────────────────┘
       │                              │
       └──────────┬───────────────────┘
                  │
                  ↓
         ┌────────────────┐
         │   CrewAI       │
         │   crew.kickoff()│
         └────────┬───────┘
                  │
                  ↓
         ┌────────────────┐
         │  Markdown      │
         │  Output        │
         └────────┬───────┘
                  │
                  │ JSON response
                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    JavaScript (marked.js CDN)                        │
│  html = marked.parse(data.result)                                   │
│  document.getElementById('result').innerHTML = html                 │
└──────┬──────────────────────────────────────────────────────────────┘
       │
       ↓
┌──────────────┐
│   UI Display │
└──────────────┘
```

---

## 5. Migration Plan

### Phase 1: Preparation (Day 1)

1. **Backup current codebase**
   ```bash
   git commit -am "Before simplification"
   git branch backup-before-simplification
   ```

2. **Verify Python environment**
   ```bash
   "C:\Users\Aravind\python_3.12\Scripts\python.exe" -c "import crewai; print('CrewAI OK')"
   ```

3. **Run existing tests** to establish baseline
   ```bash
   "C:\Users\Aravind\python_3.12\Scripts\python.exe" unit_testing/run_all_tests.py
   ```

### Phase 2: Create New Simplified Files (Day 1-2)

1. **Create new `crew_api_views.py`** (as shown in Section 3.2.1)
2. **Create new `markdown_renderer.js`** (as shown in Section 3.2.2)
3. **Create simplified `base.py`** (keep only EMI and geolocation functions)

### Phase 3: Update Frontend (Day 2)

1. **Update HTML templates** to use new API endpoint
   - Replace all `fetch('/api/fd-advisor-crew/')` calls with `fetch('/api/run-crew/')`
   - Add `crew_type` parameter to each request
   - Simplify response handling to use `marked.parse()`

2. **Update JavaScript** to use new renderer
   - Replace `renderMarkdown()` calls with new simplified version
   - Remove CrewAI-specific parsing logic

### Phase 4: Remove Old Files (Day 3)

1. **Delete** `crew_factory.py`
2. **Delete** `crews.py`
3. **Replace** `base.py` with simplified version

### Phase 5: Testing (Day 3-4)

1. **Test each crew type** via the new generic endpoint
2. **Verify Markdown rendering** works correctly
3. **Run all existing tests** to ensure no regressions

### Phase 6: Cleanup (Day 4)

1. **Remove unused imports** from remaining files
2. **Update documentation** (API docs, README)
3. **Commit changes** with descriptive message

---

## 6. Complexity Reduction Estimates

### Before Simplification

| Metric | Count |
|--------|-------|
| **Total Files** | 8 core files |
| **Total Lines** | ~5,682 lines |
| **API Endpoints** | 11 separate endpoints |
| **Crew Creation Patterns** | 3 (CrewFactory, crews.py wrappers, lazy loading) |
| **Files per Interaction** | 8-10 files |

### After Simplification

| Metric | Count | Reduction |
|--------|-------|-----------|
| **Total Files** | 5 core files | **-37.5%** (delete 3 files) |
| **Total Lines** | ~1,500 lines | **-73.6%** (save ~4,182 lines) |
| **API Endpoints** | 1 generic endpoint | **-91%** (11 → 1) |
| **Crew Creation Patterns** | 1 (direct import) | **-66%** (3 → 1) |
| **Files per Interaction** | 4-5 files | **-50%** |

### Specific File Reductions

| File | Before | After | Reduction |
|------|--------|-------|-----------|
| `crew_api_views.py` | 891 lines | ~200 lines | **-77.5%** |
| `markdown_renderer.js` | 465 lines | ~100 lines | **-78.5%** |
| `base.py` | 778 lines | ~380 lines | **-51%** |
| `crew_factory.py` | 816 lines | **DELETED** | **-100%** |
| `crews.py` | 561 lines | **DELETED** | **-100%** |

---

## 7. Features/Crews to Keep vs Remove

### 7.1 Crews to KEEP (All 11)

Based on the codebase analysis, all 11 crew types are actively used:

| Crew Type | Usage | Keep? | Reason |
|-----------|-------|-------|--------|
| **Router** | Smart Assistant intent classification | ✅ Yes | Core routing functionality |
| **Analysis** | Investment analysis queries | ✅ Yes | General data analysis |
| **Research** | Market research, news analysis | ✅ Yes | Provider data gathering |
| **Database** | SQL query generation | ✅ Yes | Database operations |
| **Visualization** | Chart generation | ✅ Yes | ECharts integration |
| **Credit Risk** | Loan approval analysis | ✅ Yes | Core banking function |
| **Loan Creation** | Loan application processing | ✅ Yes | Core banking function |
| **Mortgage Analytics** | Mortgage calculations | ✅ Yes | Specialized analytics |
| **AML** | Compliance/KYC verification | ✅ Yes | Regulatory requirement |
| **FD Advisor (TD/FD)** | FD rate analysis | ✅ Yes | Core banking function |
| **FD Template** | FD template generation | ✅ Yes | Customer-facing feature |

### 7.2 Features to Keep

- All agent definitions in [`agents.py`](Test/agents.py)
- All task definitions in [`tasks.py`](Test/tasks.py)
- All UI templates and styling
- EMI calculator functionality
- Geolocation services
- Markdown rendering (simplified)

### 7.3 Features to Remove

- CrewFactory pattern (entire [`crew_factory.py`](Test/crew_factory.py))
- Crew wrapper functions (entire [`crews.py`](Test/crews.py))
- Lazy loading infrastructure (~400 lines in [`base.py`](Test/bank_app/views/base.py:89))
- Multiple API endpoint handlers (consolidate 11 → 1)
- CrewAI-specific markdown parsing (simplify [`markdown_renderer.js`](Test/bank_app/static/js/markdown_renderer.js))

---

## 8. Risk Mitigation

### 8.1 Potential Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking existing functionality | Medium | High | Keep backup branch; test thoroughly |
| Frontend compatibility issues | Low | Medium | Update all fetch calls systematically |
| Performance degradation | Low | Low | Direct imports may actually improve performance |
| Loss of flexibility for future crews | Medium | Low | Generic endpoint supports any crew_type |

### 8.2 Rollback Plan

If issues arise:
1. Revert to `backup-before-simplification` branch
2. Investigate issues in isolated environment
3. Re-apply changes incrementally

---

## 9. Next Steps

1. **Review this plan** and provide feedback
2. **Confirm which crews/features** are actively used (if any should be removed)
3. **Switch to Code mode** to implement the simplification
4. **Execute migration plan** phase by phase

---

## Appendix: Before/After Code Examples

### A.1 Before: Complex Crew Execution

```python
# OLD: base.py lazy loader
def run_analysis_crew(*args, **kwargs):
    """Lazy wrapper for run_analysis_crew."""
    funcs = _get_crew_functions()
    if funcs and funcs['run_analysis_crew']:
        return funcs['run_analysis_crew'](*args, **kwargs)
    raise RuntimeError("run_analysis_crew not available")

# OLD: crews.py wrapper
def run_analysis_crew(user_query: str, region: str = "India"):
    try:
        return CrewFactory.run_analysis_crew(user_query=user_query, region=region)
    except CrewFactoryError as e:
        raise RuntimeError(f"Analysis crew failed: {e}")

# OLD: crew_factory.py
@staticmethod
def run_analysis_crew(user_query: str, region: str = "India") -> Any:
    crew = CrewFactory.create_analysis_crew(user_query, region)
    return crew.kickoff()

@staticmethod
def create_analysis_crew(user_query: str, region: str = "India") -> Crew:
    from agents import create_analysis_agents
    from tasks import create_analysis_tasks
    agents = create_analysis_agents(region=region)
    tasks = create_analysis_tasks(agents, user_query, region=region)
    crew = Crew(agents=[...], tasks=tasks, ...)
    return crew
```

### A.2 After: Simple Crew Execution

```python
# NEW: Direct import and execution
from agents import create_analysis_agents
from tasks import create_analysis_tasks
from crewai import Crew, Process

agents = create_analysis_agents(region="India")
tasks = create_analysis_tasks(agents, "What are FD rates?", region="India")
crew = Crew(agents=list(agents.values()), tasks=tasks, process=Process.sequential)
output = crew.kickoff()
print(output.raw)
```

### A.3 Before: Multiple API Endpoints

```python
# OLD: 11 separate endpoints
@csrf_exempt
@require_POST
def fd_advisor_crew_api(request):
    # 40 lines of duplicate error handling...
    agents = create_td_fd_agents()
    tasks = create_td_fd_tasks(agents, region=region, tenure=tenure_months)
    crew = Crew(agents=list(agents.values()), tasks=tasks, ...)
    output = crew.kickoff(...)
    return JsonResponse(format_crew_response({'result': raw_output, ...}))

@csrf_exempt
@require_POST
def credit_risk_crew_api(request):
    # Another 40 lines of duplicate error handling...
    agents = create_credit_risk_agents()
    tasks = create_credit_risk_tasks(agents, borrower_json=borrower_json)
    crew = Crew(agents=list(agents.values()), tasks=tasks, ...)
    output = crew.kickoff(...)
    return JsonResponse(format_crew_response({'result': raw_output, ...}))

# ... 9 more similar endpoints
```

### A.4 After: Single Generic Endpoint

```python
# NEW: One endpoint for all crews
CREW_FUNCTION_MAP = {
    'fd_advisor': (create_td_fd_agents, lambda a, q, r: create_td_fd_tasks(a, q)),
    'credit_risk': (create_credit_risk_agents, lambda a, q, r: create_credit_risk_tasks(a, q)),
    # ... 9 more mappings
}

@csrf_exempt
@require_POST
def run_crew(request):
    data = json.loads(request.body)
    crew_type = data.get('crew_type')
    query = data.get('query')
    
    agent_creator, task_creator = CREW_FUNCTION_MAP[crew_type]
    agents = agent_creator()
    tasks = task_creator(agents, query, region)
    
    crew = Crew(agents=list(agents.values()), tasks=tasks, process=Process.sequential)
    output = crew.kickoff()
    
    return JsonResponse({'result': output.raw, 'crew_type': crew_type})
```

---

**Document Version**: 1.0  
**Last Updated**: 2026-05-02  
**Author**: Architect Mode Analysis
