import asyncio, json, boto3
from typing import Dict, Any
from botocore.config import Config

from .config import Settings
from .utils import serialize_to_json_str
from .exceptions import LambdaExecutionError



# ==============================================================================
# ==============================================================================
def get_lambda_client(settings: Settings) -> 'boto3.client':
    boto_core_config = Config(**settings.get_boto_config())
    client_kwargs: Dict[str, Any] = {
        "service_name": 'lambda',
        "region_name": settings.region_name,
        "config": boto_core_config,
    }

    if settings.aws_access_key_id and settings.aws_secret_access_key:
        client_kwargs['aws_access_key_id'] = settings.aws_access_key_id
        client_kwargs['aws_secret_access_key'] = settings.aws_secret_access_key

    if settings.endpoint_url:
        client_kwargs['endpoint_url'] = settings.endpoint_url

    return boto3.client(**client_kwargs)


# ==============================================================================
# ==============================================================================
async def invoke_asynchronous(
    *,
    function_name: str,
    payload: Dict[str, Any],
    settings: Settings,
) -> Any:
    client = get_lambda_client(settings)
    payload_bytes = serialize_to_json_str(payload).encode('utf-8')

    def _blocking_invoke() -> Any:
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
# ==============================================================================
async def invoke_synchronous(
    *,
    function_name: str,
    payload: Dict[str, Any],
    settings: Settings,
) -> Any:
    client = get_lambda_client(settings)
    payload_bytes = serialize_to_json_str(payload).encode('utf-8')

    def _blocking_invoke() -> Any:
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