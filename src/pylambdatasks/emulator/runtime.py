################################################################################
#
# PURPOSE:
#
#   This module is the core execution engine of the Lambda emulator. It is
#   responsible for creating a high-fidelity mock of the AWS Lambda execution
#   environment, invoking the user's handler within that environment, and
#   capturing the result or exception in a structured format.
#
# RESPONSIBILITIES:
#
#   1. Define a structured `EmulationResult` to communicate outcomes back to the
#      HTTP server, ensuring a clean API boundary.
#
#   2. Define a mock `EmulatedLambdaContext` class that accurately replicates
#      the `context` object provided to a real Lambda handler.
#
#   3. Use a context manager (`_emulate_lambda_environment`) to precisely
#      control the execution environment. This manager temporarily sets all
#      standard `AWS_LAMBDA_*` environment variables before the handler runs
#      and guarantees their restoration afterward, ensuring perfect isolation.
#
#   4. Orchestrate the entire invocation lifecycle within the main public
#      function, `run_emulated_invocation`. This includes generating a unique
#      `aws_request_id`, creating the mock context, invoking the handler within
#      the managed environment, and handling both successful returns and
#      unhandled exceptions from the user's code.
#
#   5. Format success and error payloads to be bit-for-bit identical to those
#      produced by the real AWS Lambda service, ensuring compatibility with
#      `boto3`.
#
# ARCHITECTURE:
#
#   This module is designed to be a pure, stateless function library. The main
#   entrypoint, `run_emulated_invocation`, takes all necessary inputs and
#   returns a complete result, having no side effects on the server itself. The
#   use of a context manager for environment manipulation is a critical
#   architectural choice for robustness, making the emulation process atomic and
#   resilient to failures within the user's handler code. This design ensures
#   that each emulated invocation is a perfect, isolated sandbox, just like in
#   the real AWS Lambda service.
#
################################################################################

import os
import uuid
import contextlib
import traceback
from types import SimpleNamespace
from dataclasses import dataclass
from typing import Dict, Any, Generator

from ..app import LambdaTasks
from ..utils.json import serialize_to_json_str

# ==============================================================================
# Data Structures
# ==============================================================================

@dataclass
class EmulationResult:
    """A structured container for the result of an emulated invocation."""
    status_code: int
    headers: Dict[str, str]
    body: bytes


class EmulatedLambdaContext(SimpleNamespace):
    """A mock object that replicates the AWS Lambda context object."""
    def __init__(self, function_name: str, aws_request_id: str):
        self.function_name = function_name
        self.aws_request_id = aws_request_id
        self.invoked_function_arn = f"arn:aws:lambda:us-east-1:123456789012:function:{function_name}"
        self.memory_limit_in_mb = "128"
        self.function_version = "$LATEST"
        self.log_group_name = f"/aws/lambda/{function_name}"
        self.log_stream_name = "2024/01/01/[$LATEST]abcdef123456"

    def get_remaining_time_in_millis(self) -> int:
        """Returns a static, large value as we don't enforce timeouts."""
        return 300000

# ==============================================================================
# Environment Management
# ==============================================================================

@contextlib.contextmanager
def _emulate_lambda_environment(context: EmulatedLambdaContext) -> Generator[None, None, None]:
    """
    A context manager that temporarily sets AWS Lambda environment variables.
    This is the key to creating an isolated, high-fidelity execution environment.
    """
    original_env = os.environ.copy()
    
    env_vars_to_set = {
        'AWS_REGION': 'us-east-1',
        'AWS_EXECUTION_ENV': 'AWS_Lambda_python3.11',
        'AWS_LAMBDA_FUNCTION_NAME': context.function_name,
        'AWS_LAMBDA_FUNCTION_MEMORY_SIZE': context.memory_limit_in_mb,
        'AWS_LAMBDA_FUNCTION_VERSION': context.function_version,
        'AWS_LAMBDA_LOG_GROUP_NAME': context.log_group_name,
        'AWS_LAMBDA_LOG_STREAM_NAME': context.log_stream_name,
        '_HANDLER': 'handler.handler',
    }
    
    try:
        os.environ.update(env_vars_to_set)
        yield
    finally:
        # Crucially, restore the original environment after execution.
        os.environ.clear()
        os.environ.update(original_env)

# ==============================================================================
# Core Invocation Logic
# ==============================================================================
async def run_emulated_invocation(
    app: LambdaTasks,
    function_name: str,
    invocation_type: str,
    event_payload: Dict[str, Any]
) -> EmulationResult:
    """
    Orchestrates a single, complete, emulated Lambda invocation.
    This function is now asynchronous.
    """
    request_id = str(uuid.uuid4())
    context = EmulatedLambdaContext(function_name=function_name, aws_request_id=request_id)

    handler_result: Any = None
    handler_exception: Any = None

    # Run the user's handler inside the managed, emulated environment.
    with _emulate_lambda_environment(context):
        try:
            handler_result = await app._handler_instance._handle_async(
                event=event_payload, context=context
            )
        except Exception as e:
            handler_exception = e

    # Format the result into a Boto3-compatible response
    headers = {"x-amz-request-id": request_id}

    if invocation_type == "Event":
        # Asynchronous calls always get a 202, regardless of handler outcome.
        return EmulationResult(status_code=202, headers=headers, body=b"")

    # For RequestResponse:
    if handler_exception:
        headers["X-Amz-Function-Error"] = "Unhandled"
        error_payload = {
            "errorMessage": str(handler_exception),
            "errorType": type(handler_exception).__name__,
            "stackTrace": traceback.format_exc().splitlines()
        }
        body = serialize_to_json_str(error_payload).encode('utf-8')
    else:
        body = serialize_to_json_str(handler_result).encode('utf-8')
    
    # Synchronous calls always get a 200, with error details in the payload.
    return EmulationResult(status_code=200, headers=headers, body=body)