class PyLambdaTasksError(Exception):
    """
    The base exception class for all errors raised by the PyLambdaTasks library.
    
    Catching this exception will catch any error originating from this library,
    allowing for generalized error handling.
    """
    pass


# ==============================================================================
# Specific Exception Classes
# ==============================================================================

class DuplicateTaskError(PyLambdaTasksError):
    """
    Raised when attempting to register a task with a name that is already in use.
    """
    pass


class TaskNotFound(PyLambdaTasksError):
    """
    Raised by the handler when an event is received for a task name that is
    not in the registry.
    """
    pass


class InvalidEventPayload(PyLambdaTasksError):
    """
    Raised by the handler when the incoming Lambda event payload is malformed
    or missing required fields (e.g., 'task_name').
    """
    pass


class LambdaExecutionError(PyLambdaTasksError):
    """
    Raised by the synchronous broker when a 'RequestResponse' invocation
    results in a function error within the Lambda itself.

    This indicates that the invocation was successful, but the task's code
    raised an unhandled exception.
    """
    pass


class TaskParamValidationError(PyLambdaTasksError):
    """
    Raised when a task parameter fails Pydantic validation on either the
    client (``.invoke()`` / ``.delay()``) or the server (handler) side.
    """
    def __init__(self, task_name: str, param_name: str, side: str, original: Exception):
        self.task_name = task_name
        self.param_name = param_name
        self.side = side
        self.original = original
        super().__init__(
            f"Task '{task_name}': parameter '{param_name}' failed {side} validation: {original}"
        )