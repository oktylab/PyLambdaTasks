################################################################################
#
# PURPOSE:
#
#   This module is responsible for instantiating and managing the connection to
#   the Valkey server. It provides a centralized factory for creating the
#   asynchronous Valkey client used for all state management and result
#   retrieval operations.
#
# RESPONSIBILITIES:
#
#   1. Provide a single function, `get_valkey_client`, as the exclusive
#      entry point for creating or retrieving a Valkey client instance.
#
#   2. Manage a module-level singleton for the client. This ensures that a
#      single, efficient connection pool is created and reused throughout the
#      lifecycle of an application process (e.g., for the duration of a Lambda
#      container's "hot" state), preventing the overhead of re-establishing
#      connections on every operation.
#
#   3. Translate the library's `ValkeyConfig` object into the specific keyword
#      arguments required by the `valkey-py` library.
#
# ARCHITECTURE:
#
#   This module acts as the definitive boundary between PyLambdaTasks and the
#   `valkey-py` library. By centralizing client creation here, we ensure
#   consistent configuration and efficient connection management. The use of a
#   cached global instance is a pragmatic and performant choice for both the
#   short-lived Lambda environment and longer-running client applications. If the
#   underlying `valkey-py` API were to change, this would be the only module
#   requiring modification.
#
################################################################################

import valkey.asyncio as valkey
from ..config import ValkeyConfig


# # ==============================================================================
# # Valkey Client Factory
# # ==============================================================================
def get_valkey_client(valkey_config: ValkeyConfig) -> valkey.Valkey:
    """
    Creates a new instance of the asynchronous Valkey client.

    This function no longer caches the client, ensuring a fresh instance
    is created for each Lambda invocation to prevent event loop conflicts.

    Args:
        valkey_config: The dataclass containing all Valkey-related configuration.

    Returns:
        A configured instance of `valkey.asyncio.Valkey`.
    """
    # Instantiate a new client on every call.
    client_kwargs = valkey_config.get_client_config()
    return valkey.Valkey(**client_kwargs)