import ast
import sys

print("=" * 60)
print("Checking for try/except blocks that might hide exceptions")
print("=" * 60)

with open('bank_app/views.py', 'r', encoding='utf-8') as f:
    content = f.read()
    lines = content.split('\n')

tree = ast.parse(content)

# Find all try/except blocks and their line ranges
print("\nFinding try/except blocks...")
try_blocks = []
for node in ast.walk(tree):
    if isinstance(node, ast.Try):
        # Get the line range of this try block
        start_line = node.lineno
        end_line = node.end_lineno if hasattr(node, 'end_lineno') else start_line
        try_blocks.append((start_line, end_line, len(node.handlers)))
        print(f"  Try block at line {start_line}, ends at {end_line}, {len(node.handlers)} handlers")

# Check if any try/except block wraps line 842 (fd_advisor_crew_api)
print("\nChecking if line 842 is inside any try/except block...")
for start, end, handlers in try_blocks:
    if start <= 842 <= end:
        print(f"  YES: Line 842 is inside try block from {start} to {end}")
        # Print the try statement
        print(f"    Context: {lines[start-1][:80]}")
        break
else:
    print("  NO: Line 842 is NOT inside any try/except block")

# Check if there's a try/except that ends before line 842 but might have an exception
print("\nChecking for try/except blocks that end before line 842...")
for start, end, handlers in try_blocks:
    if end < 842:
        print(f"  Try block {start}-{end} ends before line 842")

# Check the indentation of line 842
print(f"\nLine 842 content: '{lines[841]}'")
print(f"Leading whitespace: {len(lines[841]) - len(lines[841].lstrip())} characters")

# Check if there's any code that might raise an exception before line 842
print("\nChecking for potential exception sources before line 842...")
for i, line in enumerate(lines[:841], start=1):
    stripped = line.strip()
    # Check for function calls that might raise exceptions
    if '(' in stripped and not stripped.startswith('#') and not stripped.startswith('def ') and not stripped.startswith('@'):
        # Check if it's at module level (no leading whitespace or minimal)
        leading = len(line) - len(line.lstrip())
        if leading < 4:  # Module level or close to it
            print(f"  Line {i}: {stripped[:60]}")

print("\n" + "=" * 60)
print("Analysis complete")
print("=" * 60)
