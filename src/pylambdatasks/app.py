import asyncio, atexit, threading, time, sys, os
from typing import List, Optional, Dict, Any, Callable
from .config import Settings
from .task import Task
from .registry import TaskRegistry
from .exceptions import TaskNotFound, InvalidEventPayload
from .dependencies import DependencyResolver
from .logger import logger


class LambdaTasks:
    ########################################################################################
    ########################################################################################
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
        logger.info(f"App: Initializing PyLambdaTasks for region '{region_name}'")
        
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

        if endpoint_url:
            logger.info(f"App: Using custom endpoint '{endpoint_url}' (Development/LocalStack mode)")
        
        logger.info(f"App: Discovery modules configured: {task_modules}")
        self.registry = TaskRegistry(task_modules=task_modules)

        self.task = Task.create_decorator(registry=self.registry, settings=self.settings)

        self._startup_hooks: List[Callable] = []
        self._shutdown_hooks: List[Callable] = []
        self._before_request_hooks: List[Callable] = []
        self._after_request_hooks: List[Callable] = []
        
        self._cold_start = True

        atexit.register(self._run_shutdown_hooks)
        logger.info("App: Instance ready. Shutdown hooks registered with atexit.")

        self.handler = self.handle

    ########################################################################################
    ########################################################################################
    def on_startup(self) -> Callable:
        def register(func: Callable) -> Callable:
            logger.info(f"App: Registered ON_STARTUP hook: '{func.__name__}'")
            self._startup_hooks.append(func)
            return func
        return register

    def on_shutdown(self) -> Callable:
        def register(func: Callable) -> Callable:
            logger.info(f"App: Registered ON_SHUTDOWN hook: '{func.__name__}'")
            self._shutdown_hooks.append(func)
            return func
        return register
        
    def before_request(self) -> Callable:
        def register(func: Callable) -> Callable:
            logger.info(f"App: Registered BEFORE_REQUEST hook: '{func.__name__}'")
            self._before_request_hooks.append(func)
            return func
        return register

    def after_request(self) -> Callable:
        def register(func: Callable) -> Callable:
            logger.info(f"App: Registered AFTER_REQUEST hook: '{func.__name__}'")
            self._after_request_hooks.append(func)
            return func
        return register
    
    ########################################################################################
    ########################################################################################
    async def _run_hooks(self, hooks: List[Callable], hook_type: str):
        if not hooks:
            return
        
        logger.info(f"Lifecycle: Executing {len(hooks)} {hook_type} hooks...")
        tasks = [
            hook() if asyncio.iscoroutinefunction(hook) else asyncio.to_thread(hook)
            for hook in hooks
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                logger.error(f"Lifecycle Error: {hook_type} hook '{hooks[i].__name__}' failed: {res}", exc_info=res)
        
        logger.info(f"Lifecycle: Finished {hook_type} hooks.")

    ########################################################################################
    ########################################################################################
    def _run_shutdown_hooks(self):
        if not self._shutdown_hooks:
            return

        logger.info(f"App: Shutdown signal received. Processing {len(self._shutdown_hooks)} hooks.")

        def runner():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._run_hooks(self._shutdown_hooks, "ON_SHUTDOWN"))
            finally:
                loop.close()

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join(timeout=5)
        if thread.is_alive():
            logger.warning("App: Shutdown hooks timed out after 5 seconds.")
        else:
            logger.info("App: Shutdown hooks completed successfully.")

    ########################################################################################
    ########################################################################################
    def handle(self, event: Dict[str, Any], context: Optional[object]) -> Any:
        return asyncio.run(self._handle_async(event, context))


########################################################################################
    ########################################################################################
    def handle(self, event: Dict[str, Any], context: Optional[object]) -> Any:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("WARNING: No running event loop detected. Creating a new event loop for this invocation.This may impact performance if the handler is invoked frequently.")
            loop = None

        if loop and loop.is_running():
            return loop.run_until_complete(self._handle_async(event, context))
        else:
            return asyncio.run(self._handle_async(event, context))

    ########################################################################################
    ########################################################################################
    async def _handle_async(self, event: Dict[str, Any], context: Optional[object]) -> Any:
        task_name = event.get("task_name", "UNKNOWN")
        start_time = time.perf_counter()
        
        extra = {
            "task_name": task_name, 
            "is_cold_start": self._cold_start,
            "aws_request_id": getattr(context, "aws_request_id", None)
        }
        
        logger.info(f"Handler: >>> Invocation started for task '{task_name}'", extra=extra)

        if self._cold_start:
            logger.info("Handler: First invocation detected. Triggering cold-start sequence.")
            await self._run_hooks(self._startup_hooks, "ON_STARTUP")
            self._cold_start = False
            logger.info("Handler: Cold-start sequence finished.")

        resolver = DependencyResolver()
        try:
            if task_name == "UNKNOWN":
                logger.error("Handler Error: Event payload is missing 'task_name' key.", extra=extra)
                raise InvalidEventPayload("Event is missing the required 'task_name' key.")

            task = self.registry.get_task(task_name)
            if not task:
                logger.error(f"Handler Error: Task '{task_name}' not found in registry.", extra=extra)
                raise TaskNotFound(f"Task '{task_name}' is not registered.")

            await self._run_hooks(self._before_request_hooks, "BEFORE_REQUEST")

            logger.info(f"Handler: Resolving dependency tree for '{task_name}'...")
            injected_kwargs = await resolver.resolve(task.dependant)
            logger.info(f"Handler: {len(injected_kwargs)} dependencies injected.")

            logger.info(f"Handler: Executing task function logic for '{task_name}'")
            result = await task.execute(event=event, injected_dependencies=injected_kwargs)
            
            duration = time.perf_counter() - start_time
            extra["duration_seconds"] = round(duration, 4)
            
            logger.info(f"Handler: <<< Task '{task_name}' succeeded in {extra['duration_seconds']}s", extra=extra)
            return result

        except Exception as e:
            duration = time.perf_counter() - start_time
            extra["duration_seconds"] = round(duration, 4)
            extra["error_type"] = type(e).__name__
            
            logger.exception(
                f"Handler Error: Task '{task_name}' failed after {extra['duration_seconds']}s. "
                f"Error: {str(e)}", 
                extra=extra
            )
            raise e

        finally:
            await self._run_hooks(self._after_request_hooks, "AFTER_REQUEST")
            await resolver.cleanup()
            logger.info(f"Handler: --- Invocation finished for '{task_name}'")
            if os.environ.get("PYLAMBDATASKS_FORCE_EXIT") == "1":
                logger.info("WARNING: PYLAMBDATASKS_FORCE_EXIT is set. Forcing process exit.")
                sys.exit(0)
