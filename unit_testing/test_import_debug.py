import sys
import ast
import traceback

print("=" * 60)
print("DEBUGGING bank_app.views import issue")
print("=" * 60)

# Check AST parsing
print("\n1. Checking AST parsing...")
with open('bank_app/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

try:
    tree = ast.parse(content)
    print('   AST parsing successful')
    
    # Find all function definitions with their line numbers
    funcs = [(node.name, node.lineno) for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    funcs.sort(key=lambda x: x[1])
    
    print(f'   Total functions found: {len(funcs)}')
    
    # Check for fd_advisor_crew_api
    fd_funcs = [f for f in funcs if 'fd_advisor' in f[0].lower()]
    print(f'   FD advisor functions: {fd_funcs}')
        
except SyntaxError as e:
    print(f'   Syntax error at line {e.lineno}: {e.msg}')
    sys.exit(1)

# Now try to import the module with detailed error tracking
print("\n2. Trying to import bank_app.views...")
print("   This will show if there's an exception during import...")

# Clear any cached imports
if 'bank_app.views' in sys.modules:
    del sys.modules['bank_app.views']
if 'bank_app' in sys.modules:
    del sys.modules['bank_app']

try:
    import bank_app.views
    print('   Module imported successfully (no exception)')
    
    # Check what attributes exist
    all_attrs = dir(bank_app.views)
    print(f'   Total attributes: {len(all_attrs)}')
    
    # Check for fd_advisor_crew_api specifically
    if hasattr(bank_app.views, 'fd_advisor_crew_api'):
        print('   SUCCESS: fd_advisor_crew_api exists!')
    else:
        print('   FAILED: fd_advisor_crew_api does NOT exist')
        
        # Check for similar names
        similar = [x for x in all_attrs if 'fd' in x.lower() or 'advisor' in x.lower()]
        print(f'   Similar attributes: {similar}')
        
        # Check if the function was defined but deleted
        print(f'   Checking if function exists in source but not in module...')
        
        # List all callable attributes
        callables = [x for x in all_attrs if not x.startswith('_') and callable(getattr(bank_app.views, x, None))]
        print(f'   First 30 callable attributes: {callables[:30]}')
        
except Exception as e:
    print(f'   Exception during import: {type(e).__name__}: {e}')
    traceback.print_exc()

print("\n3. Checking line-by-line execution...")
print("   Looking for code that might raise exceptions before line 842...")

# Read the file and check for potential issues
with open('bank_app/views.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Check lines 775-845 for any non-function code
print("   Checking lines 775-845 for module-level code...")
for i, line in enumerate(lines[774:845], start=775):
    stripped = line.strip()
    if stripped and not stripped.startswith('#') and not stripped.startswith('def ') and not stripped.startswith('@'):
        # Check if it's inside a function (has indentation)
        if line[0] == ' ' or line[0] == '\t':
            continue  # Indented, so inside a function
        else:
            print(f'   Line {i}: {stripped[:50]}')

print("\n" + "=" * 60)
print("DEBUG COMPLETE")
print("=" * 60)
