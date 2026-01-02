import asyncio, atexit, threading, time, logging
from typing import List, Optional, Dict, Any, Callable
from .config import Settings
from .task import Task
from .registry import TaskRegistry
from .exceptions import TaskNotFound, InvalidEventPayload
from .dependencies import DependencyResolver
logger = logging.getLogger("pylambdatasks")

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
        task_name = event.get("task_name", "UNKNOWN")
        
        # Injecting task_name into the logger extra so your JsonFormatter sees it
        extra = {"task_name": task_name, "lambda_event": event}
        
        logger.info(f"Task {task_name} execution started.", extra=extra)
        start_time = time.perf_counter()

        if self._cold_start:
            logger.debug("Cold start detected, running startup hooks.")
            await self._run_hooks(self._startup_hooks)
            self._cold_start = False

        resolver = DependencyResolver()
        try:
            # Task retrieval
            task = self.registry.get_task(task_name)
            if not task:
                logger.error(f"Task '{task_name}' not found in registry.", extra=extra)
                raise TaskNotFound(f"Task '{task_name}' is not registered.")

            await self._run_hooks(self._before_request_hooks)

            # Dependency resolution
            # (Note: Passing the 'task' object here to use the caching fix we discussed)
            injected_kwargs = await resolver.resolve(task.dependant)
            
            # Execute
            result = await task.execute(event=event, injected_dependencies=injected_kwargs)
            
            duration = time.perf_counter() - start_time
            extra["duration_seconds"] = round(duration, 4)
            
            logger.info(f"Task {task_name} succeeded.", extra=extra)
            return result

        except Exception as e:
            duration = time.perf_counter() - start_time
            extra["duration_seconds"] = round(duration, 4)
            
            # This triggers your AppLogger.exception -> which uses _log_and_return_id
            # and your JsonFormatter will automatically extract the full traceback.
            logger.exception(f"Task {task_name} failed after {extra['duration_seconds']}s", extra=extra, exc_info=e)
            
            # Re-raise so Lambda/Step Functions detect the failure
            raise e

        finally:
            await self._run_hooks(self._after_request_hooks)
            await resolver.cleanup()