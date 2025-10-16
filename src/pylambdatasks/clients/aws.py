################################################################################
#
# PURPOSE:
#
#   This module is responsible for the instantiation of the AWS Boto3 Lambda
#   client. It acts as a factory, translating the library's high-level
#   `AwsConfig` object into a correctly configured Boto3 client instance.
#
# RESPONSIBILITIES:
#
#   1. Provide a single function, `get_lambda_client`, as the exclusive entry
#      point for creating a Lambda client.
#
#   2. Correctly apply configuration from the `AwsConfig` object, including
#      region, timeouts, and retry settings.
#
#   3. Conditionally apply credentials (`aws_access_key_id` and
#      `aws_secret_access_key`) only if they are explicitly provided. If they
#      are omitted, Boto3 will fall back to its default credential provider
#      chain (e.g., IAM role, environment variables), which is the desired
#      behavior for production environments.
#
#   4. Critically, it applies the `endpoint_url` from the configuration. This
#      is the key mechanism that allows the library to target a local,
#      Boto3-compatible emulator for testing instead of the real AWS API.
#
# ARCHITECTURE:
#
#   This module is the definitive boundary between the PyLambdaTasks library and
#   the Boto3 SDK. No other part of the library should ever import `boto3`
#   directly. By centralizing client creation in this factory function, we
#   ensure that all clients are created and configured consistently. This design
#   makes the system easier to debug, test, and maintain. If Boto3's API
#   changes in the future, this is the only file that would need to be updated.
#
################################################################################

import boto3
from botocore.config import Config
from typing import Dict, Any

from ..config import AwsConfig

# ==============================================================================
# Boto3 Client Factory
# ==============================================================================

def get_lambda_client(aws_config: AwsConfig) -> 'boto3.client':
    """
    Creates and configures a Boto3 Lambda client based on the provided settings.

    Args:
        aws_config: The dataclass containing all AWS-related configuration.

    Returns:
        A configured Boto3 client instance for the AWS Lambda service.
    """
    # 1. Create the low-level botocore configuration for retries and timeouts.
    boto_core_config = Config(**aws_config.get_boto_config())

    # 2. Prepare the keyword arguments for the boto3.client constructor.
    client_kwargs: Dict[str, Any] = {
        "service_name": 'lambda',
        "region_name": aws_config.region_name,
        "config": boto_core_config,
    }

    # 3. Add credentials only if they are explicitly provided in the config.
    #    If not, boto3 will use its default credential resolution chain.
    if aws_config.aws_access_key_id and aws_config.aws_secret_access_key:
        client_kwargs['aws_access_key_id'] = aws_config.aws_access_key_id
        client_kwargs['aws_secret_access_key'] = aws_config.aws_secret_access_key

    # 4. Add the custom endpoint_url if provided. This is the crucial step
    #    that enables local testing against an emulator.
    if aws_config.endpoint_url:
        client_kwargs['endpoint_url'] = aws_config.endpoint_url

    # 5. Instantiate and return the client.
    return boto3.client(**client_kwargs)