import sys
import traceback

# Install a custom excepthook to catch all exceptions
original_excepthook = sys.excepthook

def custom_excepthook(exc_type, exc_value, exc_traceback):
    print("=" * 60)
    print("UNCAUGHT EXCEPTION DETECTED!")
    print("=" * 60)
    print(f"Exception type: {exc_type}")
    print(f"Exception value: {exc_value}")
    print("Traceback:")
    traceback.print_tb(exc_traceback)
    print("=" * 60)
    original_excepthook(exc_type, exc_value, exc_traceback)

sys.excepthook = custom_excepthook

print("Attempting to import bank_app.views with custom excepthook...")
print()

try:
    import bank_app.views
    print("Module imported successfully")
    print()
    
    # Check for the function
    if hasattr(bank_app.views, 'fd_advisor_crew_api'):
        print("SUCCESS: fd_advisor_crew_api exists!")
    else:
        print("FAILED: fd_advisor_crew_api does NOT exist")
        print()
        print("Checking what functions ARE defined...")
        funcs = [x for x in dir(bank_app.views) if not x.startswith('_') and callable(getattr(bank_app.views, x, None))]
        print(f"Total callable attributes: {len(funcs)}")
        print(f"First 25: {funcs[:25]}")
        
except Exception as e:
    print(f"Exception during import: {type(e).__name__}: {e}")
    traceback.print_exc()

print()
print("Import attempt complete.")
