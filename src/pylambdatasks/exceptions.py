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