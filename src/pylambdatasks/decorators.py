################################################################################
#
# PURPOSE:
#
#   This module defines the decorator responsible for converting a user's
#   Python function into a PyLambdaTasks `Task` object. It acts as the primary
#   interface for task definition within the library.
#
# RESPONSIBILITIES:
#
#   1. Provide the `TaskDecorator` class, which is instantiated by the main
#      `LambdaTasks` application.
#
#   2. The decorator (`@app.task(...)`) captures user-defined metadata,
#      including the task's unique `name` and the target `lambda_function_name`.
#
#   3. It wraps the decorated function in a `Task` object, which encapsulates
#      both the function's logic and the client-side invocation methods.
#
#   4. It registers the newly created `Task` object with the application's
#      `TaskRegistry`, making it discoverable by the handler.
#
# ARCHITECTURE:
#
#   The decorator is implemented as a callable class (`TaskDecorator`) to
#   maintain a reference to the parent application's state (the registry and
#   settings) without using global variables. When a user decorates a function,
#   they are creating a stateful `Task` instance and registering it. By
#   requiring explicit keyword arguments like `name` and `lambda_function_name`,
#   the decorator enforces a clear and unambiguous contract for defining tasks,
#   improving the overall developer experience and reducing configuration errors.
#
################################################################################

from typing import Callable, Any, Optional

# Use TYPE_CHECKING to avoid circular imports at runtime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .registry import TaskRegistry
    from .config import Settings
    from .task import Task

# ==============================================================================
# Task Decorator Class
# ==============================================================================

class TaskDecorator:
    """
    A callable class that acts as a factory for creating and registering tasks.

    An instance of this class is created as `app.task`. When called as a
    decorator (`@app.task(...)`), it transforms the decorated function into a
    `Task` object.
    """

    # --------------------------------------------------------------------------
    # Instance Initialization
    # --------------------------------------------------------------------------
    def __init__(
        self, 
        *, 
        registry: 'TaskRegistry', 
        settings: 'Settings'
    ):
        """
        Initializes the decorator with a reference to the app's registry
        and settings.
        """
        self._registry = registry
        self._settings = settings

    # --------------------------------------------------------------------------
    # Decorator Invocation
    # --------------------------------------------------------------------------
    def __call__(self, *, name: str, lambda_function_name: Optional[str] = None) -> Callable:
        """
        This method is executed when the decorator is applied to a function.
        Example: `@app.task(name="ADD_NUMBERS", lambda_function_name="my-lambda")`

        Args:
            name: The unique identifier for the task. This name is used to
                  route incoming Lambda events to the correct function.
            lambda_function_name: The name of the AWS Lambda function that will
                                  be invoked to execute this task.

        Returns:
            A wrapper function that will receive the user's function and
            complete the registration process.
        """
        if not name or not isinstance(name, str):
            raise TypeError("The task `name` must be a non-empty string.")
        # if not lambda_function_name or not isinstance(lambda_function_name, str):
        #     raise TypeError("The `lambda_function_name` must be a non-empty string.")

        def wrapper(func: Callable[..., Any]) -> 'Task':
            """
            Receives the function being decorated, creates the `Task` object,
            registers it, and returns the `Task` object to replace the original
            function in its module.
            """
            # Defer the import of `Task` to this inner function to prevent
            # a potential circular dependency at the module level.
            from .task import Task

            # Create the `Task` instance, which will encapsulate the user's
            # function and provide the client-side invocation API.
            task_instance = Task(
                func_to_execute=func,
                name=name,
                lambda_function_name=lambda_function_name,
                settings=self._settings,
            )

            # Register the task so it can be found by the handler during runtime.
            self._registry.register(task_instance)

            # Return the task instance. From this point on, any reference to
            # the decorated function's name will point to this object.
            return task_instance

        return wrapper