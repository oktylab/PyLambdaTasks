from typing import List, Optional

from .config import Settings
from .task import Task
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
        region_name: str,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        connect_timeout: int = 10,
        read_timeout: int = 60,
        total_max_attempts: int = 5,
    ):
        self.settings = Settings(
            default_lambda_function_name=default_lambda_function_name,
            region_name=region_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            endpoint_url=endpoint_url,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            total_max_attempts=total_max_attempts,
        )
        
        # Initialize the task registry, which will store a mapping of
        # task names to their corresponding Task objects.
        self.registry = TaskRegistry(task_modules=task_modules)

        self.task = Task.create_decorator(registry=self.registry, settings=self.settings)

        # Lifecycle hooks storage
        # Init hooks run during the first handler invocation (cold-start).
        # Finish hooks are attempted at process exit.
        self._init_hooks = []  # list[Callable]
        self._finish_hooks = []  # list[Callable]

        # Instantiate the handler and pass the app instance so the handler
        # may run lifecycle hooks inside the event loop on cold-start.
        self._handler_instance = Handler(registry=self.registry, settings=self.settings, app=self)

        # Expose the handler's main entrypoint method as a public attribute
        # for clean and simple use in the user's handler file.
        self.handler = self._handler_instance.handle

    # --------------------------------------------------------------------------
    # Lifecycle hook decorators
    # --------------------------------------------------------------------------
    def init(self) -> callable:
        def register(func):
            self._init_hooks.append(func)
            return func
        return register

    def finish(self) -> callable:
        def register(func):
            self._finish_hooks.append(func)
            return func
        return register