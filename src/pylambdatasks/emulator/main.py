################################################################################
#
# PURPOSE:
#
#   This module provides the core application loading logic for the PyLambdaTasks
#   framework. Its sole responsibility is to dynamically find and load a user's
#   `LambdaTasks` application instance based on a string path.
#
# RESPONSIBILITIES:
#
#   1. Provide the public `load_app_from_handler_path` function, which serves as
#      the primary entry point to this module's functionality.
#
#   2. Parse a handler string (e.g., "my_app.handler.handler") to correctly
#      identify the Python module that needs to be imported.
#
#   3. Use Python's `importlib` to dynamically load the specified module at
#      runtime.
#
#   4. Introspect the loaded module's attributes to find the singleton instance
#      of the `pylambdatasks.LambdaTasks` class.
#
# ARCHITECTURE:
#
#   This module is now designed as a pure, stateless utility library. It has
#   been intentionally decoupled from any CLI-specific logic, such as argument
#   parsing or user I/O, which now resides entirely in `pylambdatasks.cli`.
#   By centralizing the complex logic of dynamic module loading and introspection
#   here, it allows the main CLI to remain clean and focused on command handling,
#   creating a robust separation of concerns.
#
################################################################################

import importlib
from typing import Optional

from ..app import LambdaTasks

# ==============================================================================
# Application Discovery
# ==============================================================================

def _find_app_in_module(module: object) -> Optional[LambdaTasks]:
    """Scans a module's members to find an instance of the LambdaTasks app."""
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, LambdaTasks):
            return attr
    return None


def load_app_from_handler_path(handler_path: str) -> LambdaTasks:
    """
    Dynamically imports a module and finds the LambdaTasks instance within it.

    Args:
        handler_path: A string in the format 'module.submodule.handler_name'.

    Returns:
        The discovered LambdaTasks application instance.

    Raises:
        ValueError: If the handler path is malformed or the app cannot be found.
        ImportError: If the specified module cannot be imported.
    """
    if '.' not in handler_path:
        raise ValueError("Invalid handler path format. Expected 'module.handler_name'.")

    module_path, _ = handler_path.rsplit('.', 1)

    try:
        module = importlib.import_module(module_path)
        importlib.reload(module)
    except ImportError as e:
        raise ImportError(f"Could not import module '{module_path}'.") from e

    app_instance = _find_app_in_module(module)
    if not app_instance:
        raise ValueError(f"Could not find a LambdaTasks application instance in module '{module_path}'.")

    return app_instance