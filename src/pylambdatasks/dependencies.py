################################################################################
#
# PURPOSE:
#
#   This module implements a powerful and flexible dependency injection (DI)
#   system, modeled after the one in FastAPI. It allows developers to define
#   dependencies (e.g., database connections, external service clients) as
#   simple functions and have them automatically resolved and injected into
#   their task functions at runtime.
#
# RESPONSIBILITIES:
#
#   1. Provide a public `Depends` marker function. This function is used within
#      type hints (`typing.Annotated`) to signal that a parameter should be
#      injected by the DI system.
#
#   2. Define the `DependencyResolver` class, which contains the core logic for
#      the DI process.
#
#   3. Introspect a function's signature to identify parameters marked as
#      dependencies.
#
#   4. Recursively resolve the dependency graph, ensuring that dependencies of
#      dependencies are also resolved.
#
#   5. Support standard functions, async functions, and async generators as
#      dependables. Generator-based dependencies are used for resources that
#      require setup and teardown logic (e.g., `yield`ing a database session).
#
#   6. Manage the lifecycle of dependencies, including caching resolved values
#      within a single task execution and ensuring proper cleanup of resources.
#
# ARCHITECTURE:
#
#   The system is built around a short-lived `DependencyResolver` instance,
#   which is created for each task invocation. This ensures that the dependency
#   cache is isolated to a single request, preventing state leakage. Modern
#   Python features like `typing.get_type_hints` and `typing.Annotated` are
#   used for static analysis of function signatures.
#
#   For resource management (setup/teardown), the resolver leverages
#   `contextlib.AsyncExitStack`. When an async generator dependency is
#   encountered, it is entered into the exit stack. The value it yields is
#   injected into the task. After the task completes (successfully or not),
#   the `cleanup` method closes the exit stack, which automatically resumes
#   the generator, allowing its `finally` block to execute for resource cleanup.
#   This provides a robust and elegant solution for managing resources like
#   database connections.
#
################################################################################

import inspect
import typing
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Callable, Any, Dict, Optional, Annotated

# ==============================================================================
# Public API
# ==============================================================================

def Depends(dependency: Callable[..., Any]) -> Any:
    """
    Factory function used as a dependency marker in type hints.
    It doesn't do anything at runtime other than hold a reference to the
    dependency callable.
    """
    return dependency


# ==============================================================================
# Core Resolver Class
# ==============================================================================

class DependencyResolver:
    """
    Resolves and manages the lifecycle of dependencies for a single task execution.
    """

    ####################################################################
    # INSTANCE INITIALIZATION
    ####################################################################
    def __init__(self):
        # Cache to store the results of resolved dependencies for the duration
        # of a single task run. This ensures a dependency is only executed once.
        self._dependency_cache: Dict[Callable[..., Any], Any] = {}
        # An exit stack to manage the teardown of generator-based dependencies.
        self._exit_stack = AsyncExitStack()

    ####################################################################
    # PUBLIC METHODS
    ####################################################################
    async def resolve_dependencies(self, func: Callable[..., Any]) -> Dict[str, Any]:
        """
        Resolves all dependencies for a given function and returns them as a
        dictionary of keyword arguments.

        Args:
            func: The function (e.g., a task) whose dependencies need to be resolved.

        Returns:
            A dictionary mapping parameter names to their resolved dependency values.
        """
        injected_kwargs: Dict[str, Any] = {}
        
        # Use get_type_hints to correctly resolve forward-referenced type hints.
        try:
            type_hints = typing.get_type_hints(func, include_extras=True)
        except (TypeError, NameError):
            # Fallback for environments where type hints might not be resolvable.
            type_hints = {}

        for param_name, hint in type_hints.items():
            dependency_callable = self._get_dependency_from_hint(hint)
            if dependency_callable:
                resolved_value = await self._resolve_dependency_graph(dependency_callable)
                injected_kwargs[param_name] = resolved_value
        
        return injected_kwargs

    async def cleanup(self) -> None:
        """
        Cleans up any resources managed by the resolver, such as exiting
        from generator-based dependencies.
        """
        await self._exit_stack.aclose()

    ####################################################################
    # INTERNAL LOGIC
    ####################################################################
    async def _resolve_dependency_graph(self, dep_callable: Callable[..., Any]) -> Any:
        """
        Recursively resolves a single dependency and its sub-dependencies.
        """
        # If this dependency has already been resolved, return the cached value.
        if dep_callable in self._dependency_cache:
            return self._dependency_cache[dep_callable]

        # Resolve sub-dependencies for the current dependency first.
        sub_dependencies = await self.resolve_dependencies(dep_callable)

        # Execute the dependency callable with its own resolved dependencies.
        if inspect.isasyncgenfunction(dep_callable):
            # This dependency is a raw async generator. We need to wrap it to make
            # it compatible with the async context manager protocol.
            
            # 1. Wrap the generator function with the @asynccontextmanager logic.
            cm_factory = asynccontextmanager(dep_callable)
            
            # 2. Create an instance of the context manager with its dependencies.
            cm_instance = cm_factory(**sub_dependencies)
            
            # 3. Now, enter the properly wrapped context manager into the exit stack.
            resolved_value = await self._exit_stack.enter_async_context(cm_instance)

        elif inspect.iscoroutinefunction(dep_callable):
            # For async functions, await the result.
            resolved_value = await dep_callable(**sub_dependencies)
        else:
            # For regular functions, call it directly.
            resolved_value = dep_callable(**sub_dependencies)

        # Cache the result before returning.
        self._dependency_cache[dep_callable] = resolved_value
        return resolved_value

    def _get_dependency_from_hint(self, hint: Any) -> Optional[Callable[..., Any]]:
        """
        Parses a type hint to find a `Depends` marker.
        Supports `Annotated[SomeType, Depends(my_func)]`.
        """
        if typing.get_origin(hint) is Annotated:
            # The first argument of Annotated is the type, the rest is metadata.
            for meta in typing.get_args(hint)[1:]:
                # We check if the metadata *is* a callable that was wrapped
                # by our `Depends` function. Since `Depends` just returns the
                # function, we can check for callability.
                if callable(meta):
                    return meta
        return None