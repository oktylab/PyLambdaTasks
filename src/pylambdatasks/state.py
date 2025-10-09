################################################################################
#
# PURPOSE:
#
#   This module provides the complete toolkit for managing a task's lifecycle
#   state within the result backend (Valkey). It is architecturally divided
#   into two main responsibilities: client-side state creation and
#   executor-side state management.
#
# RESPONSIBILITIES:
#
#   1. Define `TaskState` Enum: Provides a source of truth for the distinct
#      lifecycle states of a task (PENDING, PROGRESS, SUCCESS, FAILED).
#
#   2. `StateManager`: An executor-facing class that manages the state of a
#      task *during* its execution. It derives the canonical `task_id` solely
#      from the `context.aws_request_id`, enforcing a clean contract with the
#      Lambda runtime (real or emulated).
#
#   3. Intelligent Key Management: Implements an advanced key schema that uses
#      Valkey hash tags (`{{{...}}}`) to ensure cluster correctness and uses
#      atomic `RENAME` operations for state transitions.
#
# ARCHITECTURE:
#
#   This module embodies the library's dual-context nature. while the `StateManager` 
#   is a stateful (for the duration of one invocation) workhorse for the executor.
#   By completely removing any reliance on special keys in the event payload
#   and depending solely on the Lambda context object, the `StateManager`
#   establishes a robust and professional boundary. This forces our local
#   emulator to be a high-fidelity replica of the real AWS environment, leading
#   to a more reliable and predictable testing experience.
#
################################################################################

import os
import sys
import time
import json
import traceback
import asyncio
from enum import Enum
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import valkey.asyncio as valkey

from .config import Settings, ValkeyConfig
from .clients.valkey import get_valkey_client
from .utils.json import serialize_to_json_str

# ==============================================================================
# Constants and Enums
# ==============================================================================

class TaskState(Enum):
    PENDING = "PENDING"
    PROGRESS = "PROGRESS"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

VALKEY_KEY_PREFIX = "pylambdatasks"

LAMBDA_RESERVED_ENV_VARS = (
    '_HANDLER',
    '_X_AMZN_TRACE_ID',
    'AWS_DEFAULT_REGION',
    'AWS_REGION',
    'AWS_EXECUTION_ENV',
    'AWS_LAMBDA_FUNCTION_NAME',
    'AWS_LAMBDA_FUNCTION_MEMORY_SIZE',
    'AWS_LAMBDA_FUNCTION_VERSION',
    'AWS_LAMBDA_INITIALIZATION_TYPE',
    'AWS_LAMBDA_LOG_GROUP_NAME',
    'AWS_LAMBDA_LOG_STREAM_NAME',
    'AWS_LAMBDA_RUNTIME_API',
    'LAMBDA_TASK_ROOT',
    'LAMBDA_RUNTIME_DIR',
    'TZ',
)

# ==============================================================================
# Key Generation Logic
# ==============================================================================

def generate_valkey_key(task_id: str, task_name: str, state: TaskState) -> str:
    """Generates the standardized Valkey key, including a cluster hash tag."""
    return f"{VALKEY_KEY_PREFIX}:{task_name}:{state.value}:{{{task_id}}}"


# ==============================================================================
# Executor-Side State Management
# ==============================================================================

class StateManager:
    """Manages the state of a single task execution inside the Lambda."""

    # --------------------------------------------------------------------------
    # Instance Initialization
    # --------------------------------------------------------------------------
    def __init__(
        self,
        *,
        context: Optional[object],
        event: Dict[str, Any],
        task_name: str,
        settings: Settings,
    ):
        self.task_id: str = self._resolve_task_id(context)
        self.task_name = task_name
        self.current_state = TaskState.PENDING
        self._settings = settings
        self._valkey: Optional[valkey.Valkey] = None
        self._start_time = time.monotonic()
        self._context = context
        self._event = event
        self._dispatch_time = self._event.get('__pylambdatasks_dispatch_time')

    @property
    def key(self) -> str:
        """The current unique key for this task in Valkey based on its state."""
        return generate_valkey_key(self.task_id, self.task_name, self.current_state)

    # --------------------------------------------------------------------------
    # Public State Transition Methods
    # --------------------------------------------------------------------------
    async def set_progress_state(self) -> None:
        """Transitions the task state to PROGRESS."""
        payload = {
            "status": TaskState.PROGRESS.value,
            "start_time_iso": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            "runtime_environment": serialize_to_json_str(self._get_lambda_runtime_env()),
        }
        if self._dispatch_time:
            payload["dispatch_time_iso"] = datetime.fromtimestamp(self._dispatch_time, tz=timezone.utc).isoformat()

        await self._transition_state(TaskState.PROGRESS, payload)

    async def set_success_state(self, result: Any) -> None:
        """Transitions the task state to SUCCESS."""
        duration = time.monotonic() - self._start_time
        payload = {
            "status": TaskState.SUCCESS.value,
            "result": serialize_to_json_str(result),
            "execution_duration_seconds": round(duration, 4),
        }
        await self._transition_state(TaskState.SUCCESS, payload)
        # await self._cleanup_pending_state()

    async def set_failure_state(self, exception: Exception) -> None:
        """Transitions the task state to FAILED."""
        duration = time.monotonic() - self._start_time
        payload = {
            "status": TaskState.FAILED.value,
            "error": serialize_to_json_str(self._format_exception(exception)),
            "execution_duration_seconds": round(duration, 4),
        }
        await self._transition_state(TaskState.FAILED, payload)
        # await self._cleanup_pending_state()

    async def update_metadata(self, metadata: Dict[str, Any]) -> None:
        """Safely merges custom metadata into the task's record."""
        valkey = await self._get_client()
        
        existing_metadata_str = await valkey.hget(self.key, "metadata")
        existing_metadata = json.loads(existing_metadata_str) if existing_metadata_str else {}
        existing_metadata.update(metadata)

        await valkey.hset(self.key, "metadata", serialize_to_json_str(existing_metadata))

    # --------------------------------------------------------------------------
    # Internal Helpers
    # --------------------------------------------------------------------------
    async def _transition_state(self, new_state: TaskState, payload: Dict[str, Any]) -> None:
        """Atomically renames the key and updates the hash for a new state."""
        valkey = await self._get_client()
        old_key = self.key
        self.current_state = new_state
        new_key = self.key
        
        expire_seconds = self._settings.valkey.task_key_expire_in_seconds

        async with valkey.pipeline() as pipe:
            # print(f"DEBUG_TIMESTAMP: {time.time_ns()} - Transitioning state from {old_key} to {new_key}")
            if (old_key != self.key and await valkey.exists(old_key)) :
                pipe.rename(old_key, new_key)
            
            pipe.hset(new_key, mapping=payload)
            pipe.expire(new_key, expire_seconds)
            await pipe.execute()

    async def _get_client(self):
        if self._valkey is None:
            self._valkey = get_valkey_client(self._settings.valkey)
            await self._valkey.ping()
        return self._valkey
    
    def _resolve_task_id(self, context: Optional[object]) -> str:
        """
        Derives the canonical task ID exclusively from the Lambda context object.
        """
        if context and hasattr(context, 'aws_request_id'):
            return context.aws_request_id
        
        raise RuntimeError(
            "Could not determine task ID. The Lambda context object is missing or "
            "does not have an 'aws_request_id' attribute. This indicates an "
            "invalid execution environment."
        )

    def _get_lambda_runtime_env(self) -> Dict[str, str]:
        """Captures key-value pairs from the Lambda runtime environment."""
        return {key: os.environ.get(key) for key in LAMBDA_RESERVED_ENV_VARS if os.environ.get(key)}

    def _format_exception(self, exception: Exception) -> Dict[str, Any]:
        exc_type, exc_value, exc_tb = sys.exc_info()
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
        return {
            "error_type": exc_type.__name__ if exc_type else "Unknown",
            "error_message": str(exc_value),
            "traceback": "".join(tb_lines),
        }
    

    # async def _cleanup_pending_state(self) -> None:
    #     """
    #     Checks for a leftover PENDING key (from a race condition), merges its
    #     data into the final state, and deletes it.
    #     """
    #     valkey = await self._get_client()
    #     pending_key = generate_valkey_key(self.task_id, self.task_name, TaskState.PENDING)
        

    #     print(f"DEBUG_TIMESTAMP: {time.time_ns()} - Checking for leftover PENDING key: {pending_key}")
    #     print(await valkey.exists(pending_key))
    #     if await valkey.exists(pending_key):
    #         pending_data = await valkey.hgetall(pending_key)
            
    #         # The most important field to preserve is 'dispatch_time_iso'.
    #         # 'arguments' should already exist, but HSET is idempotent.
    #         fields_to_merge = {
    #             k: v for k, v in pending_data.items() if k == 'dispatch_time_iso'
    #         }

    #         async with valkey.pipeline() as pipe:
    #             if fields_to_merge:
    #                 pipe.hset(self.key, mapping=fields_to_merge)
    #             # Clean up the zombie key.
    #             pipe.delete(pending_key)
    #             await pipe.execute()