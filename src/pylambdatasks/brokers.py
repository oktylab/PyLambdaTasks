import asyncio, json, boto3
from typing import Dict, Any
from botocore.config import Config

from .config import Settings
from .utils import serialize_to_json_str
from .exceptions import LambdaExecutionError




def get_lambda_client(settings: Settings) -> 'boto3.client':
    """
    Creates and configures a Boto3 Lambda client based on the provided settings.

    Args:
        aws_config: The dataclass containing all AWS-related configuration.

    Returns:
        A configured Boto3 client instance for the AWS Lambda service.
    """
    
    boto_core_config = Config(**settings.get_boto_config())
    client_kwargs: Dict[str, Any] = {
        "service_name": 'lambda',
        "region_name": settings.region_name,
        "config": boto_core_config,
    }

    # 3. Add credentials only if they are explicitly provided in the config.
    #    If not, boto3 will use its default credential resolution chain.
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        client_kwargs['aws_access_key_id'] = settings.aws_access_key_id
        client_kwargs['aws_secret_access_key'] = settings.aws_secret_access_key

    # 4. Add the custom endpoint_url if provided. This is the crucial step
    #    that enables local testing against an emulator.
    if settings.endpoint_url:
        client_kwargs['endpoint_url'] = settings.endpoint_url

    # 5. Instantiate and return the client.
    return boto3.client(**client_kwargs)


# ==============================================================================
# Asynchronous Invocation Broker ('Event')
# ==============================================================================

async def invoke_asynchronous(
    *,
    function_name: str,
    payload: Dict[str, Any],
    settings: Settings,
) -> Any:
    """
    Invokes a Lambda function asynchronously and returns its RequestId.

    Args:
        function_name: The name of the Lambda function to invoke.
        payload: The event payload to send to the function.
        settings: The application's configuration settings.

    Returns:
        The AWS RequestId for the invocation.
    """
    client = get_lambda_client(settings)
    payload_bytes = serialize_to_json_str(payload).encode('utf-8')

    def _blocking_invoke() -> Any:
        """The synchronous boto3 call to be run in a separate thread."""
        response = client.invoke(
            FunctionName=function_name,
            InvocationType='Event',
            Payload=payload_bytes,
        )

        if 'Payload' in response:
            del response['Payload']
            
        return response

    result = await asyncio.to_thread(_blocking_invoke)
    return result


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
    client = get_lambda_client(settings)
    payload_bytes = serialize_to_json_str(payload).encode('utf-8')

    def _blocking_invoke() -> Any:
        """The synchronous boto3 call to be run in a separate thread."""
        response = client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=payload_bytes,
        )

        if response.get('FunctionError'):
            error_payload_bytes = response['Payload'].read()
            error_details = error_payload_bytes.decode('utf-8')
            raise LambdaExecutionError(
                f"Lambda function '{function_name}' failed during execution: {error_details}"
            )

        result_payload_bytes = response['Payload'].read()
        return json.loads(result_payload_bytes.decode('utf-8'))

    result = await asyncio.to_thread(_blocking_invoke)
    return result