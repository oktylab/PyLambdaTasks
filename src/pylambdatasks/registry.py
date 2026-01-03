import importlib
from typing import Dict, Optional, List
from typing import TYPE_CHECKING
from .exceptions import DuplicateTaskError
from .logger import logger

if TYPE_CHECKING:
    from .task import Task


class TaskRegistry:

    ####################################################################
    ####################################################################
    def __init__(self, task_modules: List[str]):
        self._tasks: Dict[str, 'Task'] = {}
        self._tasks: Dict[str, 'Task'] = {}
        self._task_modules = task_modules
        self._discovery_done = False
        logger.info(f"Registry: Initialized with {len(task_modules)} target modules.")


    ####################################################################
    ####################################################################
    def _discover(self) -> None:
        logger.info("Discovery: Starting automated task discovery...")
        if self._discovery_done:
            logger.info("Discovery: Tasks already discovered, skipping re-import.")
            return

        self._tasks.clear() 
        
        for module_path in self._task_modules:
            try:
                logger.info(f"Discovery: Attempting to import module '{module_path}'")
                importlib.import_module(module_path)
                logger.info(f"Discovery: Successfully imported and scanned '{module_path}'")
            except ImportError as e:
                logger.error(f"Discovery Critical: Failed to import '{module_path}'. Error: {e}", exc_info=True)
                raise ImportError(f"Could not import task module '{module_path}'.") from e
        
        self._discovery_done = True
        logger.info(f"Discovery: Complete. Total unique tasks registered: {len(self._tasks)}")


    ####################################################################
    ####################################################################
    def register(self, task: 'Task') -> None:
        task_name = task.name
        lambda_target = task.lambda_function_name

        logger.info(f"Registry: Registering task '{task_name}' -> target Lambda: '{lambda_target}'")

        if task_name in self._tasks:
            existing_task = self._tasks[task_name]
            logger.error(
                f"Registry Conflict: Failed to register '{task_name}'. "
                f"Name already assigned to function '{existing_task.func_to_execute.__name__}'"
            )
            raise DuplicateTaskError(f"A task with the name '{task_name}' has already been registered. Task names must be unique.")

        self._tasks[task_name] = task
        logger.info(f"Registry: Task '{task_name}' registered successfully. Current Registry Size: {len(self._tasks)}")

    ####################################################################
    ####################################################################
    def get_task(self, name: str) -> Optional['Task']:
        logger.info(f"Registry: Search request received for task: '{name}'")
        if not self._discovery_done:
            logger.info("Registry: Discovery not yet performed. Initializing discovery now...")
            self._discover()

        task = self._tasks.get(name)
        if task:
            logger.info(f"Registry: [HIT] Task '{name}' found. Returning Task instance.")
        else:
            logger.info(f"Registry: [MISS] Task '{name}' not found. Available tasks: {list(self._tasks.keys())}")
        return task