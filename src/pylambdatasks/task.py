import inspect
from typing import Callable, Any, Dict, Annotated, Optional
from typing import get_type_hints, get_origin, get_args
from .brokers import invoke_asynchronous, invoke_synchronous
from .dependencies import get_dependant
from .logger import logger
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .config import Settings


class Task:


    ####################################################################
    ####################################################################
    def __init__(
        self,
        *,
        func_to_execute: Callable[..., Any],
        name: str,
        lambda_function_name: str,
        settings: 'Settings',
    ):
        logger.info(f"Task: Creating instance for '{name}' (Target: {lambda_function_name or 'Default'})")
        self.func_to_execute = func_to_execute
        self.name = name

        if lambda_function_name is None:
            self.lambda_function_name = settings.default_lambda_function_name
            logger.info(f"Task '{name}': Using default Lambda target '{self.lambda_function_name}'")
        else:
            self.lambda_function_name = lambda_function_name
            logger.info(f"Task '{name}': Using explicit Lambda target '{self.lambda_function_name}'")
            
        self._settings = settings

        logger.info(f"Task '{name}': Analyzing dependency tree via 'get_dependant'...")
        self.dependant = get_dependant(func_to_execute)
        logger.info(f"Task '{name}': Tree built. Found {len(self.dependant.dependencies)} injected dependencies.")

        self._full_signature = inspect.signature(self.func_to_execute)
        self._user_facing_signature = self._create_user_facing_signature()
        
        logger.info(f"Task '{name}': Initialization complete. Signature: {self._user_facing_signature}")

    ####################################################################
    ####################################################################
    @classmethod
    def create_decorator(cls, registry, settings):
        def task_decorator(*, name: str, lambda_function_name: Optional[str] = None):
            logger.info(f"Decorator: Initializing @app.task for name='{name}'")
            
            if not name or not isinstance(name, str):
                logger.error(f"Decorator Error: Invalid task name provided: {name}")
                raise TypeError("The task `name` must be a non-empty string.")
            
            def wrapper(func):
                logger.info(f"Decorator: Wrapping function '{func.__name__}' as task '{name}'")
                task_instance = cls(
                    func_to_execute=func,
                    name=name,
                    lambda_function_name=lambda_function_name,
                    settings=settings,
                )
                registry.register(task_instance)
                return task_instance
            
            return wrapper
        
        return task_decorator

    ####################################################################
    ####################################################################
    async def delay(self, *args: Any, **kwargs: Any) -> Any:
        logger.info(f"Task '{self.name}': [.delay()] preparing asynchronous dispatch.")
        payload = self._build_payload(*args, **kwargs)
        logger.info(f"Task '{self.name}': Payload built: {payload}")

        result = await invoke_asynchronous(
            function_name=self.lambda_function_name,
            payload=payload,
            settings=self._settings,
        )

        logger.info(f"Task '{self.name}': [.delay()] dispatched successfully to {self.lambda_function_name}.")
        return result

    ####################################################################
    ####################################################################
    async def invoke(self, *args: Any, **kwargs: Any) -> Any:
        logger.info(f"Task '{self.name}': [.invoke()] preparing synchronous request.")
        
        payload = self._build_payload(*args, **kwargs)
        logger.info(f"Task '{self.name}': Payload built: {payload}")

        result = await invoke_synchronous(
            function_name=self.lambda_function_name,
            payload=payload,
            settings=self._settings,
        )

        logger.info(f"Task '{self.name}': [.invoke()] request returned result: {result}")
        return result

    ####################################################################
    ####################################################################
    async def execute(
        self,
        *,
        event: Dict[str, Any],
        injected_dependencies: Dict[str, Any],
    ) -> Any:
        logger.info(f"Task '{self.name}': [execute] Extracting arguments from event...")
        function_kwargs = self._get_function_args_from_event(event)
        logger.info(f"Task '{self.name}': [execute] Merging {len(function_kwargs)} event args with {len(injected_dependencies)} injected deps.")
        final_kwargs = {**function_kwargs, **injected_dependencies}
        logger.info(f"Task '{self.name}': [execute] Calling '{self.func_to_execute.__name__}'")
        return await self.func_to_execute(**final_kwargs)
    
    ####################################################################
    ####################################################################
    def _create_user_facing_signature(self) -> inspect.Signature:
        user_facing_params = []
        for param in self._full_signature.parameters.values():
            if param.name == 'self':
                continue            
            if param.name not in self.dependant.dependencies:
                user_facing_params.append(param)
        
        new_sig = self._full_signature.replace(parameters=user_facing_params)
        return new_sig

    ####################################################################
    ####################################################################
    def _build_payload(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        valid_params = self._user_facing_signature.parameters.keys()
        extra_keys = set(kwargs.keys()) - set(valid_params)
        if extra_keys:
            logger.warning(f"Task '{self.name}': [build_payload] Ignoring unknown arguments: {extra_keys}")

        filtered_kwargs = {k: v for k, v in kwargs.items() if k in valid_params}

        try:
            bound_args = self._user_facing_signature.bind(*args, **filtered_kwargs)
            bound_args.apply_defaults()
        except TypeError as e:
            logger.error(f"Task '{self.name}': [build_payload] Signature binding failed: {e}")
            raise TypeError(f"Argument mismatch for task '{self.name}': {e}") from e

        payload = bound_args.arguments
        payload['task_name'] = self.name
        return payload
    
    ####################################################################
    ####################################################################
    def _get_function_args_from_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        extracted = {
            param_name: event[param_name]
            for param_name in self._full_signature.parameters
            if param_name in event
        }
        return extracted