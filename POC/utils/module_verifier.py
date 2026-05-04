"""
Module verification utility for agent system.

Provides functions to verify Python module installation status and
conditionally install modules only when needed.
"""

import importlib.util
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional


# Configure logging
logger = logging.getLogger(__name__)

# Default Python path as specified by user
DEFAULT_PYTHON_PATH = r"C:\Users\Aravind\python_3.12\Scripts\python.exe"


def verify_module(module_name: str, python_path: Optional[str] = None) -> bool:
    """
    Check if a Python module is installed.

    Uses importlib.util.find_spec() for verification without subprocess.

    Args:
        module_name: Name of the module to check (e.g., 'crewai', 'numpy')
        python_path: Optional path to Python interpreter. If None, uses current interpreter.

    Returns:
        True if module is installed and importable, False otherwise.
    """
    try:
        # Normalize module name (replace hyphens with underscores)
        normalized_name = module_name.replace("-", "_")

        # Use find_spec to check if module exists
        spec = importlib.util.find_spec(normalized_name)
        is_installed = spec is not None

        if is_installed:
            logger.debug(f"Module '{module_name}' is installed at: {spec.origin}")
        else:
            logger.debug(f"Module '{module_name}' is NOT installed")

        return is_installed

    except ModuleNotFoundError:
        logger.debug(f"Module '{module_name}' not found (ModuleNotFoundError)")
        return False
    except Exception as e:
        logger.warning(f"Error checking module '{module_name}': {e}")
        return False


def install_module_if_needed(
    module_name: str,
    python_path: Optional[str] = None,
    upgrade: bool = False
) -> bool:
    """
    Install a Python module only if it's not already installed.

    Args:
        module_name: Name of the module to install
        python_path: Optional path to Python interpreter. Defaults to DEFAULT_PYTHON_PATH.
        upgrade: If True, upgrade the module to latest version

    Returns:
        True if module is now installed (was already installed or successfully installed),
        False if installation failed.
    """
    # Use provided python_path or default
    actual_python_path = python_path or DEFAULT_PYTHON_PATH

    # First verify if module is already installed
    if verify_module(module_name):
        logger.info(f"Module '{module_name}' is already installed. Skipping installation.")
        return True

    logger.info(f"Module '{module_name}' not found. Initiating installation...")

    # Validate Python path exists
    if not Path(actual_python_path).exists():
        logger.error(f"Python path not found: {actual_python_path}")
        return False

    try:
        # Build pip install command
        cmd = [actual_python_path, "-m", "pip", "install"]
        if upgrade:
            cmd.append("--upgrade")
        cmd.append(module_name)

        logger.info(f"Running: {' '.join(cmd)}")

        # Execute pip install
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout for installation
        )

        if result.returncode == 0:
            logger.info(f"Successfully installed '{module_name}'")
            # Verify installation
            if verify_module(module_name):
                return True
            else:
                logger.warning(f"Installation reported success but module '{module_name}' still not found")
                return False
        else:
            logger.error(f"Failed to install '{module_name}': {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error(f"Installation of '{module_name}' timed out after 300 seconds")
        return False
    except PermissionError as e:
        logger.error(f"Permission denied while installing '{module_name}': {e}")
        return False
    except FileNotFoundError as e:
        logger.error(f"Python executable not found at '{actual_python_path}': {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error installing '{module_name}': {e}")
        return False


def verify_all_modules(
    modules: list,
    python_path: Optional[str] = None
) -> dict:
    """
    Check installation status of multiple modules.

    Args:
        modules: List of module names to check
        python_path: Optional path to Python interpreter

    Returns:
        Dictionary mapping module names to boolean (True if installed, False otherwise)
    """
    results = {}
    for module in modules:
        results[module] = verify_module(module, python_path)
    return results


def install_all_modules_if_needed(
    modules: list,
    python_path: Optional[str] = None,
    upgrade: bool = False
) -> dict:
    """
    Install multiple modules only if they're not already installed.

    Args:
        modules: List of module names to install
        python_path: Optional path to Python interpreter
        upgrade: If True, upgrade modules to latest version

    Returns:
        Dictionary mapping module names to boolean (True if installed/success, False if failed)
    """
    results = {}
    for module in modules:
        results[module] = install_module_if_needed(module, python_path, upgrade)
    return results


def get_missing_modules(
    modules: list,
    python_path: Optional[str] = None
) -> list:
    """
    Get list of modules that are not installed.

    Args:
        modules: List of module names to check
        python_path: Optional path to Python interpreter

    Returns:
        List of module names that are not installed
    """
    missing = []
    for module in modules:
        if not verify_module(module, python_path):
            missing.append(module)
    return missing


if __name__ == "__main__":
    # Example usage / basic test
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Test modules
    test_modules = ["pip", "numpy", "nonexistent_module_xyz"]

    print("\n=== Module Verification Test ===\n")

    # Verify all modules
    results = verify_all_modules(test_modules)
    print("Verification Results:")
    for module, installed in results.items():
        status = "[OK] Installed" if installed else "[MISSING] Not Installed"
        print(f" {module}: {status}")

    # Get missing modules
    missing = get_missing_modules(test_modules)
    print(f"\nMissing modules: {missing}")

    # Test installation (only for missing modules that are real)
    if missing:
        print("\nAttempting to install missing modules...")
        for module in missing:
            print(f"\nInstalling '{module}'...")
            success = install_module_if_needed(module)
            print(f"  Result: {'Success' if success else 'Failed'}")
