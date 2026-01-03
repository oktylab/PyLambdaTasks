import inspect, typing
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Callable, Any, Dict, Optional, Annotated, get_origin, get_args
from .logger import logger




####################################################################
####################################################################
class Depends:
    def __init__(self, dependency: Optional[Callable[..., Any]] = None, *, use_cache: bool = True):
        self.dependency = dependency
        self.use_cache = use_cache

    def __repr__(self) -> str:
        dep = getattr(self.dependency, '__name__', 'None')
        return f"Depends({dep}, use_cache={self.use_cache})"

def DependsFactory(dependency: Optional[Callable[..., Any]] = None, *, use_cache: bool = True) -> Any:
    return Depends(dependency=dependency, use_cache=use_cache)


####################################################################
####################################################################
class Dependant:
    def __init__(
        self, 
        call: Callable[..., Any], 
        name: Optional[str] = None, 
        is_generator: bool = False
    ):
        self.call = call
        self.name = name
        self.is_generator = is_generator
        self.dependencies: Dict[str, "Dependant"] = {}

    def __repr__(self) -> str:
        return f"<Dependant call={self.call.__name__} deps={list(self.dependencies.keys())}>"

####################################################################
####################################################################
def get_dependant(call: Callable[..., Any], name: Optional[str] = None) -> Dependant:
    call_name = getattr(call, '__name__', str(call))
    logger.info(f"DI Analysis: Examining function '{call_name}' (Target Param: '{name or 'Root'}')")

    is_gen = inspect.isasyncgenfunction(call) or inspect.isgeneratorfunction(call)
    dependant = Dependant(call=call, name=name, is_generator=is_gen)

    logger.info(f"DI Analysis: Resolving type hints for '{call_name}'...")
    try:
        type_hints = typing.get_type_hints(call, include_extras=True)
        logger.info(f"DI Analysis: Successfully resolved hints for '{call_name}'. Found {len(type_hints)} typed parameters.")
    except (TypeError, NameError) as e:
        logger.warning(f"DI Analysis: Could not resolve hints for '{call_name}' due to {type(e).__name__}. Falling back to empty hints.")
        type_hints = {}

    for param_name, hint in type_hints.items():
        dep_info = _extract_depends(hint)
        if dep_info and dep_info.dependency:
            sub_dep_name = getattr(dep_info.dependency, '__name__', 'unnamed')
            logger.info(f"DI Analysis: Found sub-dependency on parameter '{param_name}' -> '{sub_dep_name}'")
            
            sub_dependant = get_dependant(call=dep_info.dependency, name=param_name)
            dependant.dependencies[param_name] = sub_dependant

    logger.info(f"DI Analysis: Completed tree for '{call_name}'.")
    return dependant


####################################################################
####################################################################
def _extract_depends(hint: Any) -> Optional[Depends]:
    origin = get_origin(hint)
    if origin is Annotated:
        args = get_args(hint)
        logger.info(f"Hint Parser: Annotated type detected. Metadata length: {len(args[1:])}")
        
        for arg in args[1:]:
            if isinstance(arg, Depends):
                dep_name = getattr(arg.dependency, '__name__', 'unnamed')
                logger.info(f"Hint Parser: Found explicit 'Depends' marker for function: '{dep_name}'")
                return arg
            
            if callable(arg) and not isinstance(arg, type):
                call_name = getattr(arg, '__name__', 'unnamed')
                logger.info(f"Hint Parser: Found raw callable dependency: '{call_name}'. Wrapping in Depends.")
                return Depends(dependency=arg)
    
    return None

####################################################################
####################################################################
class DependencyResolver:
    def __init__(self):
        self._dependency_cache: Dict[Callable[..., Any], Any] = {}
        self._exit_stack = AsyncExitStack()
        logger.info("DI Resolver: Initialized new resolver session and AsyncExitStack.")

    async def resolve(self, dependant: Dependant) -> Dict[str, Any]:
        parent_name = dependant.call.__name__
        logger.info(f"DI Resolver: Resolving {len(dependant.dependencies)} sub-dependencies for '{parent_name}'")
        
        values: Dict[str, Any] = {}
        
        for param_name, sub_dep in dependant.dependencies.items():
            resolved_value = await self._solve(sub_dep)
            values[param_name] = resolved_value
            
        return values

    async def _solve(self, dependant: Dependant) -> Any:
        call = dependant.call
        call_name = call.__name__
        
        if call in self._dependency_cache:
            logger.info(f"DI Resolver: [CACHE HIT] Reusing already resolved value for '{call_name}'")
            return self._dependency_cache[call]

        logger.info(f"DI Resolver: [EXEC] Solving tree for '{call_name}'")
        sub_values = await self.resolve(dependant)

        value = None
        if dependant.is_generator:
            logger.info(f"DI Resolver: [GEN] Entering generator context for '{call_name}'")
            if inspect.isasyncgenfunction(call):
                cm = asynccontextmanager(call)(**sub_values)
            else:
                cm = asynccontextmanager(asynccontextmanager(call))(**sub_values)
            
            value = await self._exit_stack.enter_async_context(cm)
        elif inspect.iscoroutinefunction(call):
            logger.info(f"DI Resolver: [AWAIT] Calling async dependency '{call_name}'")
            value = await call(**sub_values)
        else:
            logger.info(f"DI Resolver: [CALL] Calling sync dependency '{call_name}'")
            value = call(**sub_values)

        self._dependency_cache[call] = value
        logger.info(f"DI Resolver: [SUCCESS] '{call_name}' resolved and cached.")
        return value

    async def cleanup(self) -> None:
        logger.info("DI Resolver: Starting cleanup. Exiting all AsyncExitStack contexts...")
        await self._exit_stack.aclose()
        logger.info("DI Resolver: Cleanup complete. All dependencies closed.")