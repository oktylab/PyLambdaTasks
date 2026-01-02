import inspect
import typing
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Callable, Any, Dict, Optional, Annotated, List, Union, get_origin, get_args

# ==============================================================================
# ==============================================================================

class Depends:
    def __init__(self, dependency: Optional[Callable[..., Any]] = None, *, use_cache: bool = True):
        self.dependency = dependency
        self.use_cache = use_cache

    def __repr__(self) -> str:
        dep = getattr(self.dependency, '__name__', 'None')
        return f"Depends({dep})"

def DependsFactory(dependency: Optional[Callable[..., Any]] = None, *, use_cache: bool = True) -> Any:
    """Factory function to maintain the Depends() syntax."""
    return Depends(dependency=dependency, use_cache=use_cache)

# ==============================================================================
# ==============================================================================

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
        # Map of parameter_name -> Dependant object
        self.dependencies: Dict[str, "Dependant"] = {}

# ==============================================================================
# ==============================================================================

def get_dependant(call: Callable[..., Any], name: Optional[str] = None) -> Dependant:
    """
    Recursively analyzes a function and builds a tree of Dependant objects.
    This replaces runtime typing.get_type_hints calls.
    """
    is_gen = inspect.isasyncgenfunction(call) or inspect.isgeneratorfunction(call)
    dependant = Dependant(call=call, name=name, is_generator=is_gen)

    try:
        # Resolve hints once during analysis
        type_hints = typing.get_type_hints(call, include_extras=True)
    except (TypeError, NameError):
        type_hints = {}

    for param_name, hint in type_hints.items():
        dep_info = _extract_depends(hint)
        if dep_info and dep_info.dependency:
            # Recursively build the tree for this sub-dependency
            sub_dependant = get_dependant(call=dep_info.dependency, name=param_name)
            dependant.dependencies[param_name] = sub_dependant

    return dependant

def _extract_depends(hint: Any) -> Optional[Depends]:
    """Helper to find Depends() in Annotated types."""
    if get_origin(hint) is Annotated:
        for arg in get_args(hint)[1:]:
            if isinstance(arg, Depends):
                return arg
            # Support the old way: Annotated[T, Depends(func)] where Depends is just a callable
            if callable(arg) and not isinstance(arg, type):
                return Depends(dependency=arg)
    return None

# ==============================================================================
# ==============================================================================

class DependencyResolver:
    """
    Resolves a pre-built Dependant tree. 
    NO get_type_hints calls happen here.
    """

    def __init__(self):
        self._dependency_cache: Dict[Callable[..., Any], Any] = {}
        self._exit_stack = AsyncExitStack()

    async def resolve(self, dependant: Dependant) -> Dict[str, Any]:
        """
        Resolves sub-dependencies for a Dependant and returns kwargs.
        """
        values: Dict[str, Any] = {}
        
        for param_name, sub_dep in dependant.dependencies.items():
            resolved_value = await self._solve(sub_dep)
            values[param_name] = resolved_value
            
        return values

    async def _solve(self, dependant: Dependant) -> Any:
        call = dependant.call
        
        # FastAPI-style caching for the duration of the request
        if call in self._dependency_cache:
            return self._dependency_cache[call]

        # Solve sub-dependencies recursively
        sub_values = await self.resolve(dependant)

        if dependant.is_generator:
            # Handle sync/async generators
            if inspect.isasyncgenfunction(call):
                cm = asynccontextmanager(call)(**sub_values)
            else:
                # Wrap sync generator for async exit stack
                cm = asynccontextmanager(asynccontextmanager(call))(**sub_values)
            
            value = await self._exit_stack.enter_async_context(cm)
        elif inspect.iscoroutinefunction(call):
            value = await call(**sub_values)
        else:
            value = call(**sub_values)

        self._dependency_cache[call] = value
        return value

    async def cleanup(self) -> None:
        await self._exit_stack.aclose()