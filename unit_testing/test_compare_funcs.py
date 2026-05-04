import ast
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("=" * 60)
print("Comparing AST functions vs. imported module functions")
print("=" * 60)

views_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Test', 'bank_app', 'views.py')
with open(views_path, 'r', encoding='utf-8') as f:
    content = f.read()

tree = ast.parse(content)

# Get all function definitions from AST
ast_funcs = [(node.name, node.lineno) for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
ast_funcs.sort(key=lambda x: x[1])

print(f"\nAST found {len(ast_funcs)} functions:")
for name, lineno in ast_funcs:
    print(f"  Line {lineno}: {name}")

# Now import the module and check what's actually defined
print("\n" + "-" * 60)
print("Importing module and checking actual functions...")
print("-" * 60)

# Clear cache
for mod in list(sys.modules.keys()):
    if 'bank_app' in mod:
        del sys.modules[mod]

import bank_app.views

# Get all function attributes from the module
module_funcs = []
for name in dir(bank_app.views):
    if not name.startswith('_'):
        attr = getattr(bank_app.views, name)
        if callable(attr) and hasattr(attr, '__module__') and attr.__module__ == 'bank_app.views':
            module_funcs.append(name)

print(f"\nModule has {len(module_funcs)} callable attributes from bank_app.views:")
for name in sorted(module_funcs):
    print(f"  {name}")

# Compare
print("\n" + "=" * 60)
print("Comparison:")
print("=" * 60)

ast_func_names = set(name for name, _ in ast_funcs)
module_func_names = set(module_funcs)

print(f"\nFunctions in AST but NOT in module:")
missing = ast_func_names - module_func_names
for name in sorted(missing):
    # Find the line number
    for n, ln in ast_funcs:
        if n == name:
            print(f"  {name} (line {ln})")
            break

print(f"\nFunctions in module but NOT in AST:")
extra = module_func_names - ast_func_names
for name in sorted(extra):
    print(f"  {name}")

print("\n" + "=" * 60)
