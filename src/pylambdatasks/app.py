import asyncio, atexit, threading
from typing import List, Optional, Dict, Any, Callable
from .config import Settings
from .task import Task
from .registry import TaskRegistry
from .exceptions import TaskNotFound, InvalidEventPayload
from .dependencies import DependencyResolver


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
        connect_timeout: Optional[int] = None,
        read_timeout: Optional[int] = None,
        total_max_attempts: Optional[int] = None,
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


        # Container lifecycle hooks
        self._startup_hooks: List[Callable] = []
        self._shutdown_hooks: List[Callable] = []

        # Invocation lifecycle hooks
        self._before_request_hooks: List[Callable] = []
        self._after_request_hooks: List[Callable] = []
        
        # Track cold starts for the @on_startup hook
        self._cold_start = True

        # Register the shutdown hooks to run when the Python process exits.
        atexit.register(self._run_shutdown_hooks)

        # Expose the handler method
        self.handler = self.handle

    # --------------------------------------------------------------------------
    # Lifecycle hook decorators
    # --------------------------------------------------------------------------
    def on_startup(self) -> Callable:
        """Decorator to register a function to run only on cold-start."""
        def register(func: Callable) -> Callable:
            self._startup_hooks.append(func)
            return func
        return register

    def on_shutdown(self) -> Callable:
        """Decorator to register a function to run when the Lambda container shuts down."""
        def register(func: Callable) -> Callable:
            self._shutdown_hooks.append(func)
            return func
        return register
        
    def before_request(self) -> Callable:
        """Decorator to register a function to run before each invocation."""
        def register(func: Callable) -> Callable:
            self._before_request_hooks.append(func)
            return func
        return register

    def after_request(self) -> Callable:
        """Decorator to register a function to run after each invocation."""
        def register(func: Callable) -> Callable:
            self._after_request_hooks.append(func)
            return func
        return register

    # --------------------------------------------------------------------------
    # Hook Runners
    # --------------------------------------------------------------------------
    async def _run_hooks(self, hooks: List[Callable]):
        """Executes a list of sync or async hooks concurrently."""
        if not hooks: return
        tasks = [
            hook() if asyncio.iscoroutinefunction(hook) else asyncio.to_thread(hook)
            for hook in hooks
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    def _run_shutdown_hooks(self):
        """
        Special synchronous runner for atexit. It creates its own event loop
        in a separate thread to run async shutdown hooks.
        """
        if not self._shutdown_hooks: return

        def runner():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._run_hooks(self._shutdown_hooks))
            finally:
                loop.close()

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join(timeout=5)

    ####################################################################
    # MAIN HANDLER LOGIC
    ####################################################################
    def handle(self, event: Dict[str, Any], context: Optional[object]) -> Any:
        return asyncio.run(self._handle_async(event, context))

    async def _handle_async(self, event: Dict[str, Any], context: Optional[object]) -> Any:
        if self._cold_start:
            await self._run_hooks(self._startup_hooks)
            self._cold_start = False

        resolver = DependencyResolver()
        try:
            task_name = event.get("task_name")
            if not task_name:
                raise InvalidEventPayload("Event is missing the required 'task_name' key.")

            task = self.registry.get_task(task_name)
            if not task:
                raise TaskNotFound(f"Task '{task_name}' is not registered.")

            await self._run_hooks(self._before_request_hooks)
            injected_kwargs = await resolver.resolve_dependencies(task.func_to_execute)
            result = await task.execute(event=event, injected_dependencies=injected_kwargs)
            return result

        finally:
            await self._run_hooks(self._after_request_hooks)
            await resolver.cleanup()