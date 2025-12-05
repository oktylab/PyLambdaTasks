import inspect
from typing import Callable, Any, Dict, Annotated, Optional
from typing import get_type_hints, get_origin, get_args
from .brokers import invoke_asynchronous, invoke_synchronous


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .config import Settings


class Task:
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


    @classmethod
    def create_decorator(cls, registry, settings):
        """
        Creates the @app.task decorator factory.
        """
        def task_decorator(*, name: str, lambda_function_name: Optional[str] = None):
            if not name or not isinstance(name, str):
                raise TypeError("The task `name` must be a non-empty string.")
            
            def wrapper(func):
                # Create Task instance (using cls, so no circular import needed)
                task_instance = cls(
                    func_to_execute=func,
                    name=name,
                    lambda_function_name=lambda_function_name,
                    settings=settings,
                )
                # Register with the app
                registry.register(task_instance)
                return task_instance
            
            return wrapper
        
        return task_decorator
    
    # --------------------------------------------------------------------------
    # Public Client API (Used for invoking the task)
    # --------------------------------------------------------------------------
    async def delay(self, *args: Any, **kwargs: Any) -> Any:
        """
        Asynchronously invokes the task ('Event' invocation type).
        """

        payload = self._build_payload(*args, **kwargs)

        result = await invoke_asynchronous(
            function_name=self.lambda_function_name,
            payload=payload,
            settings=self._settings,
        )

        return result

    async def invoke(self, *args: Any, **kwargs: Any) -> Any:
        """
        Synchronously invokes the task and waits for the result
        ('RequestResponse' invocation type).
        """

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
    ) -> Any:
        """
        Executes the wrapped business logic with the provided event payload
        and dependencies. This is for internal, server-side use only.
        """
        function_kwargs = self._get_function_args_from_event(event)
        final_kwargs = {**function_kwargs, **injected_dependencies}

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
        valid_params = self._user_facing_signature.parameters.keys()
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in valid_params}

        try:
            bound_args = self._user_facing_signature.bind(*args, **filtered_kwargs)

        except TypeError as e:
            raise TypeError(f"Argument mismatch for task '{self.name}': {e}") from e

        payload = bound_args.arguments
        payload['task_name'] = self.name
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