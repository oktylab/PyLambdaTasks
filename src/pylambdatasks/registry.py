################################################################################
#
# PURPOSE:
#
#   This module defines the `TaskRegistry` class, a central component that acts
#   as a collection or catalog for all tasks defined within an application. It
#   maintains a mapping between a task's unique string name and its
#   corresponding `Task` object.
#
# RESPONSIBILITIES:
#
#   1. Storage: It provides an in-memory dictionary to store registered tasks.
#
#   2. Registration: It exposes a `register` method, used by the `TaskDecorator`
#      to add newly created `Task` objects to the collection.
#
#   3. Conflict Detection: During registration, it actively checks for duplicate
#      task names and raises a specific `DuplicateTaskError`. This provides
#      immediate, clear feedback to the developer if two tasks are accidentally
#      given the same name, preventing silent overwrites and runtime ambiguity.
#
#   4. Lookup: It exposes a `get_task` method, used by the `Handler` to safely
#      retrieve a `Task` object based on the name provided in an invocation
#      event.
#
# ARCHITECTURE:
#
#   The `TaskRegistry` is designed as a pure data structure manager. It has no
#   external dependencies on clients like AWS or Valkey and contains no complex
#   business logic. It is instantiated once by the `LambdaTasks` application and
#   is passed by reference to the components that need to interact with it
#   (the decorator for writing, the handler for reading). This clean separation
#   ensures its role is simple, predictable, and easy to test in isolation.
#
################################################################################

import importlib
import sys
from typing import Dict, Optional, List

# Forward reference for type hinting to avoid circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .task import Task


# ==============================================================================
# Custom Exceptions
# ==============================================================================

class DuplicateTaskError(Exception):
    """
    Raised when attempting to register a task with a name that is already in use.
    """
    pass


# ==============================================================================
# Task Registry Class
# ==============================================================================

class TaskRegistry:
    """

    Manages the collection of all tasks available to the application.
    """

    ####################################################################
    # INSTANCE INITIALIZATION
    ####################################################################
    def __init__(self, task_modules: List[str]):
        """
        Initializes a new, empty TaskRegistry.
        """
        self._tasks: Dict[str, 'Task'] = {}
        self._tasks: Dict[str, 'Task'] = {}
        self._task_modules = task_modules
        self._discovery_done = False




    def _discover(self) -> None:
        """
        Imports all configured task modules to trigger decorator registration.
        This method is idempotent and should only run once.
        """
        if self._discovery_done:
            return

        for module_path in self._task_modules:
            try:
                # Reload module if already imported to support local dev reloading
                if module_path in sys.modules:
                    importlib.reload(sys.modules[module_path])
                else:
                    importlib.import_module(module_path)
            except ImportError as e:
                raise ImportError(f"Could not import task module '{module_path}'.") from e
        
        self._discovery_done = True

    ####################################################################
    # PUBLIC METHODS
    ####################################################################
    def register(self, task: 'Task') -> None:
        """
        Adds a Task object to the registry.

        Args:
            task: The `Task` instance to be registered.

        Raises:
            DuplicateTaskError: If a task with the same name already exists
                                in the registry.
        """
        task_name = task.name
        if task_name in self._tasks:
            raise DuplicateTaskError(
                f"A task with the name '{task_name}' has already been registered. "
                "Task names must be unique."
            )

        self._tasks[task_name] = task

    def get_task(self, name: str) -> Optional['Task']:
        """
        Retrieves a task from the registry by its unique name.

        Args:
            name: The name of the task to retrieve.

        Returns:
            The `Task` object if found, otherwise `None`.
        """
        self._discover()
        return self._tasks.get(name)