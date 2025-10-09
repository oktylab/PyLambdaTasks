################################################################################
#
# PURPOSE:
#
#   This module acts as the invocation broker for the library. It is the single
#   point of contact for communicating with the AWS Lambda API, whether it is
#   the real AWS service or a local, Boto3-compatible emulator.
#
# RESPONSIBILITIES:
#
#   1. Provide `invoke_asynchronous` for 'Event' type invocations, which
#      dispatches a task and immediately returns the RequestId.
#
#   2. Provide `invoke_synchronous` for 'RequestResponse' type invocations,
#      which dispatches a task, waits for its completion, and returns the result.
#
#   3. Use the `boto3` client, configured via `AwsConfig`, to perform all API
#      calls. This allows it to seamlessly target a local `endpoint_url`.
#
#   4. Execute blocking `boto3` network calls in a separate thread using
#      `asyncio.to_thread` to prevent stalling the application's event loop.
#
#   5. Handle the details of payload serialization and response parsing,
#      including robust error handling for failed synchronous invocations.
#
# ARCHITECTURE:
#
#   This module is a stateless utility that completely abstracts away the AWS
#   SDK. By centralizing all `boto3` interactions here, the rest of the
#   client-side code (like `task.py`) remains clean and focused on its own
#   logic. The decision to always use `boto3` and control the destination via
#   configuration is a key architectural choice that eliminates the need for
#   separate "local" and "remote" logic paths, dramatically simplifying the
#   library and improving its robustness.
#
################################################################################

import asyncio
import json
from typing import Dict, Any

from .config import Settings
from .clients.aws import get_lambda_client
from .utils.json import serialize_to_json_str
from .exceptions import LambdaExecutionError

# ==============================================================================
# Asynchronous Invocation Broker ('Event')
# ==============================================================================

async def invoke_asynchronous(
    *,
    function_name: str,
    payload: Dict[str, Any],
    settings: Settings,
) -> str:
    """
    Invokes a Lambda function asynchronously and returns its RequestId.

    Args:
        function_name: The name of the Lambda function to invoke.
        payload: The event payload to send to the function.
        settings: The application's configuration settings.

    Returns:
        The AWS RequestId for the invocation.
    """
    client = get_lambda_client(settings.aws)
    payload_bytes = serialize_to_json_str(payload).encode('utf-8')

    def _blocking_invoke() -> str:
        """The synchronous boto3 call to be run in a separate thread."""
        response = client.invoke(
            FunctionName=function_name,
            InvocationType='Event',
            Payload=payload_bytes,
        )
        # The RequestId is the key to linking the call to the execution.
        return response['ResponseMetadata']['RequestId']

    # Run the blocking I/O call in a thread to avoid stalling the event loop.
    request_id = await asyncio.to_thread(_blocking_invoke)
    return request_id


# ==============================================================================
# Synchronous Invocation Broker ('RequestResponse')
# ==============================================================================

async def invoke_synchronous(
    *,
    function_name: str,
    payload: Dict[str, Any],
    settings: Settings,
) -> Any:
    """
    Invokes a Lambda function synchronously and returns its result payload.

    If the invoked Lambda function raises an exception, this function will
    raise a `LambdaExecutionError`.

    Args:
        function_name: The name of the Lambda function to invoke.
        payload: The event payload to send to the function.
        settings: The application's configuration settings.

    Returns:
        The JSON-decoded payload returned by the Lambda function.
    """
    client = get_lambda_client(settings.aws)
    payload_bytes = serialize_to_json_str(payload).encode('utf-8')

    def _blocking_invoke() -> Any:
        """The synchronous boto3 call to be run in a separate thread."""
        response = client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=payload_bytes,
        )

        # print(response)  # For debugging purposes.
        # Check if the Lambda function itself reported an error.
        if response.get('FunctionError'):
            error_payload_bytes = response['Payload'].read()
            error_details = error_payload_bytes.decode('utf-8')
            raise LambdaExecutionError(
                f"Lambda function '{function_name}' failed during execution: {error_details}"
            )

        # Read the streaming body, decode it, and parse the JSON result.
        result_payload_bytes = response['Payload'].read()
        return json.loads(result_payload_bytes.decode('utf-8'))

    # Run the blocking I/O call in a thread.
    result = await asyncio.to_thread(_blocking_invoke)
    return result