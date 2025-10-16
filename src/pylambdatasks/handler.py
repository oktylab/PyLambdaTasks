################################################################################
#
# PURPOSE:
#
#   This module defines the `Handler` class, which contains the core
#   "executor-side" logic for the PyLambdaTasks library. Its responsibility is
#   to process incoming invocation events from the AWS Lambda runtime, orchestrate
#   the execution of the appropriate task, and manage its state.
#
# RESPONSIBILITIES:
#
#   1. Event Parsing and Validation: It extracts the `task_name` and other
#      essential metadata from the Lambda event payload. It performs initial
#      checks to ensure the payload is well-formed.
#
#   2. Task Routing: It uses the application's `TaskRegistry` to look up the
#      `Task` object corresponding to the `task_name` from the event.
#
#   3. State Management Orchestration: It instantiates a `StateManager` for
#      the task execution. It is responsible for signaling the start of the
#      task (`PROGRESS`), and its final state (`SUCCESS` or `FAILED`).
#
#   4. Dependency Resolution: It orchestrates the dependency injection
#      process, solving for any dependencies required by the target task
#      function before execution.
#
#   5. Task Execution: It invokes the actual business logic of the user's
#      function with the correct arguments and injected dependencies.
#
#   6. Error Handling: It provides a robust top-level try/except block to
#      catch any exceptions during task execution, ensuring that failures are
#      properly logged to the state backend before re-raising the exception.
#
# ARCHITECTURE:
#
#   The `Handler` is designed as a stateless service class. It is instantiated
#   once by the `LambdaTasks` application and holds references to shared
#   components like the registry and settings. Its main method, `handle`, is
#   fully re-entrant and encapsulates the entire lifecycle of a single task
#   invocation. This design aligns perfectly with the AWS Lambda execution
#   model, where a single handler instance may process multiple invocations
#   sequentially. All state specific to a single invocation is managed in
#   short-lived objects created within the `handle` method itself.
#
################################################################################

import asyncio
import atexit
import threading
from typing import Dict, Any, Optional

from .config import Settings
from .registry import TaskRegistry
from .exceptions import TaskNotFound, InvalidEventPayload
from .dependencies import DependencyResolver
from .state import StateManager


class Handler:
    """
    Orchestrates the server-side execution of a task within the Lambda
    environment.
    """

    ####################################################################
    # INSTANCE INITIALIZATION
    ####################################################################
    def __init__(self, *, registry: TaskRegistry, settings: Settings, app: Optional[object] = None):
        """
        Initializes the handler with references to the application's core
        components.

        Args:
            registry: The configured TaskRegistry containing all discovered tasks.
            settings: The application's central configuration object.
            app: The LambdaTasks application instance (optional). If provided,
                 its registered init/finish hooks will be executed at the
                 appropriate times.
        """
        self._registry = registry
        self._settings = settings
        self._app = app

        # Track whether we've already executed init hooks (cold-start handling).
        self._cold_start = True

        # Register finish hooks to run at process exit (execute async hooks by
        # creating a temporary loop in a background thread).
        if getattr(self._app, "_finish_hooks", None):
            atexit.register(self._run_finish_hooks_at_exit)

    # Helper to run a hook inside an event loop safely (supports async & sync).
    async def _run_hook_maybe_async(self, hook):
        if asyncio.iscoroutinefunction(hook):
            await hook()
        else:
            # Run sync hooks off the event loop to avoid blocking.
            await asyncio.to_thread(hook)

    # Runs finish hooks at process exit by creating a temporary event loop
    # inside a background thread so async coroutines can be awaited.
    def _run_finish_hooks_at_exit(self):
        finish_hooks = getattr(self._app, "_finish_hooks", []) or []
        if not finish_hooks:
            return

        def _runner():
            loop = asyncio.new_event_loop()
            try:
                async def _run_all():
                    for h in finish_hooks:
                        try:
                            if asyncio.iscoroutinefunction(h):
                                await h()
                            else:
                                # sync hook -> run in thread to avoid blocking the loop
                                await asyncio.to_thread(h)
                        except Exception:
                            # Swallow exceptions during teardown
                            pass
                loop.run_until_complete(_run_all())
            finally:
                loop.close()

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        # Wait briefly to allow teardown to progress; do not block indefinitely.
        t.join(timeout=5)

    ####################################################################
    # MAIN HANDLER ENTRYPOINT
    ####################################################################
    def handle(self, event: Dict[str, Any], context: Optional[object]) -> Any:
        """
        The main entrypoint for the AWS Lambda runtime. This method is called
        for each invocation of the Lambda function.

        Args:
            event: The event payload from the Lambda invocation. This is
                   expected to be a JSON object (dictionary).
            context: The AWS Lambda context object, providing runtime
                     information.

        Returns:
            The result of the task execution, which will be serialized and
            returned to the caller in a RequestResponse invocation.
        """
        # AWS Lambda handlers can be either sync or async. We delegate to an
        # async method and run it to completion to support the async nature
        # of the library's internal components (e.g., valkey client, async
        # dependencies).
        return asyncio.run(self._handle_async(event, context))

    ####################################################################
    # ASYNCHRONOUS CORE LOGIC
    ####################################################################
    async def _handle_async(self, event: Dict[str, Any], context: Optional[object]) -> Any:
        """
        The core asynchronous logic for handling a task invocation.
        """
        # If this is the cold-start, run registered init hooks inside the
        # current event loop so async hooks are properly awaited.
        if self._cold_start and getattr(self._app, "_init_hooks", None):
            for hook in self._app._init_hooks:
                try:
                    await self._run_hook_maybe_async(hook)
                except Exception:
                    # Ignore init hook errors to avoid preventing handler startup.
                    pass
            self._cold_start = False

        # 1. Extract Task Name from the event payload.
        task_name = event.get("task_name")
        if not task_name:
            raise InvalidEventPayload("Event is missing the required 'task_name' key.")

        # 2. Look up the corresponding Task object in the registry.
        task = self._registry.get_task(task_name)
        if not task:
            raise TaskNotFound(f"Task '{task_name}' is not registered.")


        # 3. Initialize the StateManager for this specific invocation.
        state_manager = StateManager(
            event=event,
            context=context,
            task_name=task.name,
            settings=self._settings,
        )

        # 4. Resolve dependencies and execute the task within a managed context.
        resolver = DependencyResolver()
        try:
            # Announce that the task is starting and set its initial state.
            await state_manager.set_progress_state()
            # Resolve all dependencies required by the user's function.
            injected_kwargs = await resolver.resolve_dependencies(task.func_to_execute)
            
            # Execute the user's actual business logic.
            result = await task.execute(
                event=event,
                injected_dependencies=injected_kwargs,
                state_manager=state_manager,
            )

            # If execution was successful, record the success state.
            await state_manager.set_success_state(result)

            return result

        except Exception as e:
            # If any exception occurred, record the failure state.
            await state_manager.set_failure_state(e)
            raise e

        finally:
            # 5. Ensure any resources used by dependencies are properly cleaned up.
            await resolver.cleanup()