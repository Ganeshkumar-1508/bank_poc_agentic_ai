import sys
import traceback

# Clear any cached imports
for mod in list(sys.modules.keys()):
    if 'bank_app' in mod:
        del sys.modules[mod]

# Try to import with detailed error tracking
print('Attempting to import bank_app.views...')
try:
    import bank_app.views
    print('Import successful')
    
    # Check if the function exists
    if hasattr(bank_app.views, 'fd_advisor_crew_api'):
        print('SUCCESS: fd_advisor_crew_api exists')
    else:
        print('FAILED: fd_advisor_crew_api does NOT exist')
        
        # Check what functions DO exist
        funcs = [x for x in dir(bank_app.views) if not x.startswith('_') and callable(getattr(bank_app.views, x, None))]
        print(f'Total functions: {len(funcs)}')
        
        # Check for crew-related functions
        crew_funcs = [x for x in funcs if 'crew' in x.lower()]
        print(f'Crew functions found: {crew_funcs}')
        
        # Check for all functions containing 'fd' or 'advisor'
        fd_funcs = [x for x in funcs if 'fd' in x.lower() or 'advisor' in x.lower()]
        print(f'FD/Advisor functions found: {fd_funcs}')
        
except Exception as e:
    print(f'Exception during import: {type(e).__name__}: {e}')
    traceback.print_exc()

print('Done.')
