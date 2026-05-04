"""
Central dependency checker for the bank_poc_agentic_ai project.

This script verifies all required Python modules are installed and
provides options to install missing dependencies.
"""

import argparse
import logging
import sys
import os
from typing import List, Dict

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import the module verifier
try:
    from .module_verifier import (
        verify_module,
        install_module_if_needed,
        verify_all_modules,
        install_all_modules_if_needed,
        get_missing_modules,
        DEFAULT_PYTHON_PATH
    )
except ImportError:
    from module_verifier import (
        verify_module,
        install_module_if_needed,
        verify_all_modules,
        install_all_modules_if_needed,
        get_missing_modules,
        DEFAULT_PYTHON_PATH
    )


# Define required modules for different components
REQUIRED_MODULES = {
    "core": [
        "django",
        "streamlit",
        "pandas",
        "numpy",
    ],
    "crewai": [
        "crewai",
        "crewai-tools",
        "langchain",
        "langchain-community",
    ],
    "database": [
        "sqlalchemy",
        "psycopg2-binary",
        "sqlite3",  # Built-in, but listed for completeness
    ],
    "ml": [
        "scikit-learn",
        "xgboost",
        "tensorflow",
        "torch",
    ],
    "visualization": [
        "matplotlib",
        "seaborn",
        "plotly",
        "echarts",
    ],
    "email": [
        "google-auth",
        "google-auth-oauthlib",
        "google-auth-httplib2",
        "google-api-python-client",
    ],
    "news": [
        "newsapi-python",
        "requests",
    ],
    "neo4j": [
        "neo4j",
    ],
    "pdf": [
        "reportlab",
        "fpdf2",
    ],
}

# All modules combined
ALL_REQUIRED_MODULES = []
for category_modules in REQUIRED_MODULES.values():
    ALL_REQUIRED_MODULES.extend(category_modules)


def check_dependencies(
    categories: List[str] = None,
    python_path: str = None,
    verbose: bool = False
) -> Dict[str, Dict[str, bool]]:
    """
    Check installation status of required dependencies.

    Args:
        categories: List of category names to check (e.g., ['core', 'crewai'])
                   If None, checks all categories.
        python_path: Optional path to Python interpreter
        verbose: If True, print detailed output

    Returns:
        Dictionary mapping category names to {module: is_installed} dicts
    """
    categories_to_check = categories or list(REQUIRED_MODULES.keys())
    results = {}

    for category in categories_to_check:
        if category not in REQUIRED_MODULES:
            logger.warning(f"Unknown category: {category}")
            continue

        modules = REQUIRED_MODULES[category]
        results[category] = verify_all_modules(modules, python_path)

        if verbose:
            installed_count = sum(1 for v in results[category].values() if v)
            total_count = len(results[category])
            print(f"\n{category.upper()}: {installed_count}/{total_count} installed")
            for module, installed in results[category].items():
                status = "[OK]" if installed else "[MISSING]"
                print(f"  {status} {module}")

    return results


def install_missing_dependencies(
    categories: List[str] = None,
    python_path: str = None,
    upgrade: bool = False,
    interactive: bool = True
) -> Dict[str, Dict[str, bool]]:
    """
    Install missing dependencies for specified categories.

    Args:
        categories: List of category names to install
        python_path: Optional path to Python interpreter
        upgrade: If True, upgrade existing packages
        interactive: If True, ask for confirmation before installing

    Returns:
        Dictionary mapping category names to {module: success} dicts
    """
    categories_to_install = categories or list(REQUIRED_MODULES.keys())
    results = {}

    for category in categories_to_install:
        if category not in REQUIRED_MODULES:
            logger.warning(f"Unknown category: {category}")
            continue

        modules = REQUIRED_MODULES[category]
        missing = get_missing_modules(modules, python_path)

        if not missing:
            logger.info(f"All {category} dependencies already installed")
            results[category] = {m: True for m in modules}
            continue

        print(f"\nMissing {category} dependencies: {', '.join(missing)}")

        if interactive:
            response = input(f"Install {len(missing)} missing {category} packages? (y/n): ")
            if response.lower() != 'y':
                logger.info(f"Skipping installation for {category}")
                # Still return current status
                results[category] = verify_all_modules(modules, python_path)
                continue

        logger.info(f"Installing missing {category} dependencies...")
        results[category] = install_all_modules_if_needed(modules, python_path, upgrade)

        # Report results
        failed = [m for m, success in results[category].items() if not success]
        if failed:
            logger.error(f"Failed to install: {', '.join(failed)}")
        else:
            logger.info(f"Successfully installed all {category} dependencies")

    return results


def generate_report(python_path: str = None) -> str:
    """
    Generate a comprehensive dependency report.

    Args:
        python_path: Optional path to Python interpreter

    Returns:
        Formatted report string
    """
    lines = []
    lines.append("=" * 60)
    lines.append("DEPENDENCY VERIFICATION REPORT")
    lines.append("=" * 60)
    lines.append(f"Python path: {python_path or 'default (current interpreter)'}")
    lines.append("")

    results = check_dependencies(verbose=False)

    total_installed = 0
    total_missing = 0

    for category, module_status in results.items():
        installed = sum(1 for v in module_status.values() if v)
        missing = sum(1 for v in module_status.values() if not v)
        total_installed += installed
        total_missing += missing

        lines.append(f"\n[{category.upper()}]")
        for module, is_installed in module_status.items():
            status = "[OK] Installed" if is_installed else "[MISSING] Missing"
            lines.append(f"  {module}: {status}")

    lines.append("")
    lines.append("=" * 60)
    lines.append(f"SUMMARY: {total_installed} installed, {total_missing} missing")
    lines.append("=" * 60)

    return "\n".join(lines)


def main():
    """Main entry point for command-line usage."""
    parser = argparse.ArgumentParser(
        description="Check and install project dependencies"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check dependencies (default behavior)"
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install missing dependencies"
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        choices=list(REQUIRED_MODULES.keys()) + ["all"],
        help="Categories to check/install (default: all)"
    )
    parser.add_argument(
        "--python",
        type=str,
        default=DEFAULT_PYTHON_PATH,
        help=f"Python interpreter path (default: {DEFAULT_PYTHON_PATH})"
    )
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="Upgrade existing packages"
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate detailed report"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    # Handle categories
    categories = args.categories
    if categories and "all" in categories:
        categories = list(REQUIRED_MODULES.keys())

    if args.report:
        print(generate_report(args.python))
        return

    if args.check or not args.install:
        results = check_dependencies(categories, args.python, args.verbose)
        missing_count = sum(
            1 for cat in results.values() for v in cat.values() if not v
        )
        if missing_count > 0:
            print(f"\n[WARNING] {missing_count} dependencies missing. Run with --install to fix.")
            sys.exit(1)
        else:
            print("\n[OK] All dependencies satisfied")
            sys.exit(0)
    
        if args.install:
            results = install_missing_dependencies(
                categories, args.python, args.upgrade, interactive=True
            )
            failed_count = sum(
                1 for cat in results.values() for v in cat.values() if not v
            )
            if failed_count > 0:
                print(f"\n[ERROR] {failed_count} packages failed to install")
                sys.exit(1)
            else:
                print("\n[OK] All dependencies installed successfully")
                sys.exit(0)


if __name__ == "__main__":
    main()
