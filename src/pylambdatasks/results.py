################################################################################
#
# PURPOSE:
#
#   This module defines the `AsyncResult` class, which is the primary
#   client-side interface for interacting with a dispatched task. It acts as a
#   "future" or a handle to a remote task execution, allowing the user to check
#   its status and retrieve its result.
#
# RESPONSIBILITIES:
#
#   1. Encapsulate a `task_id`, which is the unique identifier linking this
#      object to a specific task execution record in the result backend.
#
#   2. Provide a public `.get()` method to asynchronously fetch the current
#      state and result of the task from Valkey.
#
#   3. Intelligently locate the task's record in Valkey. Since the record's key
#      changes based on its state (e.g., PENDING, SUCCESS), it uses a pattern
#      search (`KEYS`) to find the key associated with the `task_id`.
#
#   4. Handle the deserialization of the stored data, converting the raw hash
#      from Valkey into a clean Python dictionary.
#
# ARCHITECTURE:
#
#   An `AsyncResult` object is a simple, stateless handle. It is created and
#   returned by `task.delay()` and contains just enough information (the task ID
#   and settings) to perform its function. The logic for finding the task key
#   is designed for efficiency and correctness in a clustered Valkey environment.
#   By including the task ID in a hash tag (`{{{...}}}`) in the key schema, we
#   ensure that a `KEYS` command is only ever executed on a single cluster node,
#   avoiding a full cluster scan and making the operation performant.
#
################################################################################

import json
from typing import Dict, Any

# Use TYPE_CHECKING to avoid circular imports at runtime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .config import Settings

from .clients.valkey import get_valkey_client
from .state import VALKEY_KEY_PREFIX

# ==============================================================================
# AsyncResult Class
# ==============================================================================

class AsyncResult:
    """
    A client-side handle to a remote task execution.
    """

    # --------------------------------------------------------------------------
    # Instance Initialization
    # --------------------------------------------------------------------------
    def __init__(self, *, task_id: str, settings: 'Settings'):
        """
        Initializes the AsyncResult handle.

        Args:
            task_id: The unique ID of the task execution to track.
            settings: The application's central configuration object.
        """
        self.task_id = task_id
        self._settings = settings
        self._valkey = None

    # --------------------------------------------------------------------------
    # Public API
    # --------------------------------------------------------------------------
    async def get(self) -> Dict[str, Any]:
        """
        Retrieves the current state and result of the task from the backend.
        
        If no record is found for the task, it is assumed to be in a
        'PENDING' state.

        Returns:
            A dictionary representing the task's current state record.
        """
        valkey = await self._get_client()

        # Find the key for this task_id. The state part of the key is a wildcard.
        # The hash tag ensures this command is efficient on a cluster.
        key_pattern = f"{VALKEY_KEY_PREFIX}:*:*:{{{self.task_id}}}"
        keys_found = await valkey.keys(key_pattern)

        if not keys_found:
            return {"status": "PENDING", "task_id": self.task_id}

        # There should only ever be one key for a given task_id.
        task_key = keys_found[0]
        state_raw = await valkey.hgetall(task_key)

        return self._deserialize_state(state_raw)

    # --------------------------------------------------------------------------
    # Internal Helpers
    # --------------------------------------------------------------------------
    async def _get_client(self):
        """Lazily initializes and returns the Valkey client."""
        if self._valkey is None:
            self._valkey = get_valkey_client(self._settings.valkey)
            await self._valkey.ping()
        return self._valkey

    def _deserialize_state(self, state_raw: Dict[str, str]) -> Dict[str, Any]:
        """
        Parses the raw string dictionary from Valkey into a Python dictionary
        with appropriate types, decoding JSON fields.
        """
        decoded_state: Dict[str, Any] = {}
        json_fields = ('arguments', 'result', 'error', 'metadata', 'runtime_environment')

        for key, value in state_raw.items():
            if key in json_fields:
                try:
                    decoded_state[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    # If decoding fails, return the raw value.
                    decoded_state[key] = value
            else:
                decoded_state[key] = value
        
        return decoded_state