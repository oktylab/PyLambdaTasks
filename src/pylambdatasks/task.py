################################################################################
#
# PURPOSE:
#
#   This module defines the `Task` class, which is the core object-oriented
#   abstraction for a user-defined task. When a developer decorates a function
#   with `@app.task`, that function is replaced by an instance of this `Task`
#   class.
#
# RESPONSIBILITIES:
#
#   1. Encapsulation: It holds the user's original function, its unique name,
#      and the critical configuration required to invoke it, such as the target
#      `lambda_function_name`.
#
#   2. Client-Side API: It provides the public `.delay()` (asynchronous) and
#      `.invoke()` (synchronous) methods. These methods are responsible for
#      binding only the user-facing arguments into a payload and delegating
#      invocation to the broker.
#
#   3. Executor-Side API: It provides the `.execute()` method, used exclusively
#      by the `Handler` inside the Lambda environment, to run the original
#      business logic with server-side arguments and injected dependencies.
#
# ARCHITECTURE:
#
#   The `Task` class intelligently separates the client's view of a function's
#   signature from the executor's view. Upon initialization, it introspects the
#   user's function and creates two signature objects: a complete signature for
#   server-side execution, and a filtered "user-facing" signature that excludes
#   any internally injected parameters (like `self` or `Depends`). This is the
#   key to providing a clean client-side API (`.delay(a=1, b=2)`) while still
#   supporting powerful server-side features like state management and
#   dependency injection.
#
################################################################################

import inspect, time
from typing import Callable, Any, Dict, Annotated
from typing import get_type_hints, get_origin, get_args

# Use TYPE_CHECKING to avoid circular imports at runtime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .config import Settings
    from .state import StateManager
    from .results import AsyncResult
    from .dependencies import Depends

# ==============================================================================
# Task Class
# ==============================================================================

class Task:
    """
    An object representing a remotely executable function, providing a clean
    API for both invocation and execution.
    """

    # --------------------------------------------------------------------------
    # Instance Initialization
    # --------------------------------------------------------------------------
    def __init__(
        self,
        *,
        func_to_execute: Callable[..., Any],
        name: str,
        lambda_function_name: str,
        settings: 'Settings',
    ):
        """
        Initializes a Task instance. This is done by the @app.task decorator.
        """
        self.func_to_execute = func_to_execute
        self.name = name

        if lambda_function_name is None:
            self.lambda_function_name = settings.default_lambda_function_name
        else : 
            self.lambda_function_name = lambda_function_name
            
        self._settings = settings

        # The full signature, used by the executor for dependency injection.
        self._full_signature = inspect.signature(self.func_to_execute)
        # A filtered signature for client-side validation, excluding internal params.
        self._user_facing_signature = self._create_user_facing_signature()

    # --------------------------------------------------------------------------
    # Public Client API (Used for invoking the task)
    # --------------------------------------------------------------------------
    async def delay(self, *args: Any, **kwargs: Any) -> 'AsyncResult':
        """
        Asynchronously invokes the task ('Event' invocation type).

        This method dispatches the task for execution and immediately returns
        an `AsyncResult` object.
        """
        from .brokers import invoke_asynchronous
        from .results import AsyncResult

        payload = self._build_payload(*args, **kwargs)

        request_id = await invoke_asynchronous(
            function_name=self.lambda_function_name,
            payload=payload,
            settings=self._settings,
        )

        return AsyncResult(task_id=request_id, settings=self._settings)

    async def invoke(self, *args: Any, **kwargs: Any) -> Any:
        """
        Synchronously invokes the task and waits for the result
        ('RequestResponse' invocation type).
        """
        from .brokers import invoke_synchronous

        payload = self._build_payload(*args, **kwargs)

        result = await invoke_synchronous(
            function_name=self.lambda_function_name,
            payload=payload,
            settings=self._settings,
        )

        return result

    # --------------------------------------------------------------------------
    # Public Executor API (Used by the handler inside Lambda)
    # --------------------------------------------------------------------------
    async def execute(
        self,
        *,
        event: Dict[str, Any],
        injected_dependencies: Dict[str, Any],
        state_manager: 'StateManager'
    ) -> Any:
        """
        Executes the wrapped business logic with the provided event payload
        and dependencies. This is for internal, server-side use only.
        """
        function_kwargs = self._get_function_args_from_event(event)
        final_kwargs = {**function_kwargs, **injected_dependencies}

        if 'self' in self._full_signature.parameters:
            final_kwargs['self'] = state_manager

        return await self.func_to_execute(**final_kwargs)

    # --------------------------------------------------------------------------
    # Internal Helper Methods
    # --------------------------------------------------------------------------
    def _create_user_facing_signature(self) -> inspect.Signature:
        """
        Introspects the original function and creates a new signature that
        excludes any internally injected parameters ('self' or Depends).

        This is the crucial method that prevents TypeErrors on the client side.
        """
        # We need to import here to avoid a circular dependency at the module level.
        from .dependencies import Depends
        
        try:
            type_hints = get_type_hints(self.func_to_execute, include_extras=True)
        except (TypeError, NameError):
            type_hints = {}
        
        user_facing_params = []
        for param in self._full_signature.parameters.values():
            # Rule 1: Exclude the special 'self' parameter for state management.
            if param.name == 'self':
                continue
            
            # Rule 2: Exclude any parameter marked with our 'Depends' marker.
            is_dependency = False
            hint = type_hints.get(param.name)
            
            # Using get_origin and get_args for robust type inspection.
            # This correctly identifies Annotated types even when aliased.
            if hint and get_origin(hint) is Annotated:
                # The first argument of Annotated is the type, the rest is metadata.
                for meta in get_args(hint)[1:]:
                    # Our Depends() function just returns the callable.
                    if callable(meta):
                        is_dependency = True
                        break
            
            if not is_dependency:
                user_facing_params.append(param)
                
        return self._full_signature.replace(parameters=user_facing_params)


    def _build_payload(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """
        Binds provided arguments to the USER-FACING signature to create a
        serializable event payload.
        """
        try:
            # This now correctly uses the filtered signature for client-side calls.
            bound_args = self._user_facing_signature.bind(*args, **kwargs)
            bound_args.apply_defaults()
        except TypeError as e:
            raise TypeError(f"Argument mismatch for task '{self.name}': {e}") from e

        payload = bound_args.arguments
        payload['task_name'] = self.name
        payload['__pylambdatasks_dispatch_time'] = time.time() 
        return payload

    def _get_function_args_from_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extracts only the arguments relevant to the user function from an event,
        ensuring no metadata keys are accidentally passed.
        """
        return {
            param_name: event[param_name]
            for param_name in self._full_signature.parameters
            if param_name in event
        }