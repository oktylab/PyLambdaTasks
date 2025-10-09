################################################################################
#
# PURPOSE:
#
#   This module defines the main `LambdaTasks` application class. It serves as
#   the primary entry point and central coordinator for the entire library.
#   Users will instantiate this class to configure their Lambda environment,

#   expose the main handler for AWS Lambda to invoke.
#
# RESPONSIBILITIES:
#
#   1. Configuration Management: It accepts and holds the AWS and Valkey
#      configurations, making them accessible to other parts of the library
#      through a unified settings object.
#
#   2. Task Registry Ownership: It initializes and owns the `TaskRegistry`,
#      which keeps track of all functions decorated as tasks.
#
#   3. Decorator Factory: It exposes the task decorator (`@app.task`). By
#      linking the decorator to the app instance, we ensure that tasks are

#
#   4. Handler Exposure: It instantiates the `Handler` class (which contains
#      the core execution logic) and exposes its main `handle` method. This
#      provides a clean and simple entry point for the user's `handler.py`
#      file (e.g., `handler = app.handler`).
#
# ARCHITECTURE:
#
#   The `LambdaTasks` class is designed as a high-level orchestrator. It does
#   not contain complex logic for task invocation, execution, or state
#   management itself. Instead, it delegates these responsibilities to
#   specialized classes (`TaskDecorator`, `Handler`, `TaskRegistry`).
#
################################################################################

from typing import List, Optional

from .config import Settings, AwsConfig, ValkeyConfig
from .decorators import TaskDecorator
from .handler import Handler
from .registry import TaskRegistry


class LambdaTasks:
    """
    The main application class for creating and managing a task-driven
    AWS Lambda application.
    """

    ####################################################################
    # INSTANCE INITIALIZATION
    ####################################################################
    def __init__(
        self,
        *,
        task_modules: List[str],
        default_lambda_function_name: str,
        aws_config: Optional[AwsConfig] = None,
        valkey_config: Optional[ValkeyConfig] = None,
    ):
        """
        Initializes the LambdaTasks application and its components.

        This sets up the configuration, task registry, and the task decorator,
        but does not yet discover or load any tasks.

        Args:
            aws_config: Configuration for the AWS client (boto3). Required for
                        invoking tasks from a client context.
            valkey_config: Configuration for the Valkey client. Required for
                           state tracking and result storage.
        """
        # Initialize the central settings object that will be used
        # throughout the library to access configuration.

        self.settings = Settings(
            aws_config=aws_config, 
            valkey_config=valkey_config,
            default_lambda_function_name=default_lambda_function_name,
        )

        # Initialize the task registry, which will store a mapping of
        # task names to their corresponding Task objects.
        self.registry = TaskRegistry(task_modules=task_modules)

        # Create the task decorator instance. By passing the registry to it,
        # any function decorated with `@app.task` will be automatically
        # registered with this application instance.
        self.task = TaskDecorator(registry=self.registry, settings=self.settings)

        # Instantiate the handler, which contains the logic for executing a
        # task when the Lambda function is invoked.
        self._handler_instance = Handler(registry=self.registry, settings=self.settings)

        # Expose the handler's main entrypoint method as a public attribute
        # for clean and simple use in the user's handler file.
        self.handler = self._handler_instance.handle