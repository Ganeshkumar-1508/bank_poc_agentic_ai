import sys
sys.path.insert(0, '.')

# Force reload
if 'rag_engine' in sys.modules:
    del sys.modules['rag_engine']
if 'middleware' in sys.modules:
    del sys.modules['middleware']

import rag_engine
import middleware

print("rag_engine functions:", [x for x in dir(rag_engine) if not x.startswith('_')])
print()
print("Has query_rag:", hasattr(rag_engine, 'query_rag'))
print()
print("middleware classes:", [x for x in dir(middleware) if not x.startswith('_')])
print()
print("Has AuditContextMiddleware:", hasattr(middleware, 'AuditContextMiddleware'))
