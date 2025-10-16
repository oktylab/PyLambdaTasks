################################################################################
#
# PURPOSE:
#
#   This module defines a hierarchy of custom exception classes for the
#   PyLambdaTasks library. Using custom exceptions allows consumers of the
#   library to write specific, targeted error-handling logic.
#
# RESPONSIBILITIES:
#
#   1. Define a base `PyLambdaTasksError` class from which all other library-
#      specific exceptions inherit. This provides a single, catch-all exception
#      for users who want to handle any error originating from this library.
#
#   2. Define specific, descriptive exception classes for various predictable
#      error conditions, such as configuration issues, task registration
#      conflicts, and runtime invocation failures.
#
# ARCHITECTURE:
#
#   The module implements a simple and clear inheritance tree:
#
#       Exception
#           └── PyLambdaTasksError (Base class for all library exceptions)
#               ├── ConfigurationError
#               ├── DuplicateTaskError
#               ├── TaskNotFound
#               ├── InvalidEventPayload
#               └── LambdaExecutionError
#
#   By centralizing all exception definitions in this single file, we create a
#   canonical source of truth for error types, making them easy for both the
#   library's internal code and external user code to import and use.
#
################################################################################

# ==============================================================================
# Base Exception
# ==============================================================================

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

class ConfigurationError(PyLambdaTasksError):
    """
    Raised when a required configuration is missing or invalid.
    """
    pass


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