################################################################################
#
# PURPOSE:
#
#   This module defines the configuration model for the PyLambdaTasks library.
#   It provides structured, type-safe classes for users to define their AWS
#   and Valkey connection settings. It also houses the main `Settings` class,
#   which acts as the single source of truth for configuration throughout the
#   application's lifecycle.
#
# RESPONSIBILITIES:
#
#   1. Define `ConfigurationError` for clear, library-specific exceptions
#      related to misconfiguration.
#
#   2. Define `AwsConfig` and `ValkeyConfig` dataclasses. These classes
#      validate user input and encapsulate the logic for translating high-level
#      settings into the specific dictionary formats required by underlying
#      client libraries (boto3, valkey-py).
#
#   3. The `AwsConfig` model now includes an `endpoint_url`, which is the
#      standard boto3 parameter for targeting a custom endpoint like a local
#      emulator (e.g., LocalStack or our own).
#
#   4. Define the `Settings` class, which holds the configured instances of
#      `AwsConfig` and `ValkeyConfig`.
#
# ARCHITECTURE:
#
#   The use of dataclasses enforces a clear and explicit contract for what
#   configuration is required. By centralizing all settings into a single
#   `Settings` object that is passed down to components that need it, we avoid
#   global state and make the system's dependencies explicit. This design
#   greatly simplifies testing, as mock `Settings` objects can be easily
#   injected during unit tests. The inclusion of `endpoint_url` is a critical
#   architectural choice that enables seamless local testing by leveraging
#   boto3's native capabilities instead of building a parallel, non-standard
#   invocation mechanism.
#
################################################################################

import socket
from dataclasses import dataclass, field
from typing import Dict, Optional, Any

# ==============================================================================
# Custom Exceptions
# ==============================================================================

class ConfigurationError(Exception):
    """
    Raised when a required configuration is missing or invalid.
    """
    pass


# ==============================================================================
# Client-Specific Configuration Models
# ==============================================================================

@dataclass
class AwsConfig:
    """
    Configuration for the AWS Boto3 client.
    """
    # --- Standard AWS Credentials ---
    region_name: str
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None

    # --- BotoCore Configuration ---
    connect_timeout: int = 10
    read_timeout: int = 60
    total_max_attempts: int = 5

    # --- Local Testing Endpoint ---
    # This is the key field for enabling local, boto3-compatible testing.
    # Set this to a URL like "http://localhost:9000" to target a local emulator.
    # If None, boto3 will target the default AWS endpoints.
    endpoint_url: Optional[str] = None


    def get_boto_config(self) -> Dict[str, Any]:
        """
        Returns a dictionary formatted for the botocore.config.Config object.
        """
        return {
            "connect_timeout": self.connect_timeout,
            "read_timeout": self.read_timeout,
            "retries": {
                'total_max_attempts': self.total_max_attempts,
                'mode': 'standard'
            },
        }


@dataclass
class ValkeyConfig:
    """
    Configuration for the Valkey client, used as the result and state backend.
    """
    host: str
    port: int
    password: Optional[str] = None
    username: Optional[str] = None
    
    # --- SSL OPTIONS ---
    ssl: bool = False
    ssl_cert_reqs: Optional[str] = None

    # --- SOCKET AND TIMEOUT OPTIONS ---
    socket_connect_timeout: Optional[int] = 10
    socket_keepalive: Optional[bool] = True
    
    # Use a default_factory for mutable types like dictionaries
    socket_keepalive_options: Optional[Dict[int, int]] = field(
        default_factory=lambda: {
            socket.TCP_KEEPIDLE: 60,
            socket.TCP_KEEPINTVL: 30,
            socket.TCP_KEEPCNT: 5,
        }
    )

    # --- TASK-SPECIFIC OPTIONS ---
    # Default TTL for completed task results is 24 hours.
    task_key_expire_in_seconds: int = 86400

    def get_client_config(self) -> Dict[str, Any]:
        """
        Returns a dictionary formatted for the valkey.Valkey client constructor.
        """
        config = {
            "host": self.host,
            "port": self.port,
            "password": self.password,
            "username": self.username,
            "ssl": self.ssl,
            "decode_responses": True, # Keep this hardcoded for library consistency
        }
        
        # --- Conditionally add options to avoid passing `None` ---
        # This is important because valkey-py might treat `param=None` differently
        # than omitting the parameter entirely.
        
        if self.ssl_cert_reqs is not None:
            config["ssl_cert_reqs"] = self.ssl_cert_reqs
        
        if self.socket_connect_timeout is not None:
            config["socket_connect_timeout"] = self.socket_connect_timeout
            
        if self.socket_keepalive is not None:
            config["socket_keepalive"] = self.socket_keepalive
            
        if self.socket_keepalive_options is not None:
            config["socket_keepalive_options"] = self.socket_keepalive_options
            
        return config




# ==============================================================================
# Central Settings Container
# ==============================================================================

class Settings:
    """
    A container for the application's runtime configuration.
    
    This object is instantiated by `LambdaTasks` and passed to components
    that require access to configuration values.
    """
    def __init__(
        self,
        *,
        default_lambda_function_name: str,
        aws_config: Optional[AwsConfig] = None,
        valkey_config: Optional[ValkeyConfig] = None,
    ):
        self._aws_config = aws_config
        self._valkey_config = valkey_config
        self._default_lambda_function_name = default_lambda_function_name
        

    @property
    def aws(self) -> AwsConfig:
        """
        Provides access to the AWS configuration.

        Raises:
            ConfigurationError: If AWS config was not provided during
                                application initialization.
        """
        if self._aws_config is None:
            raise ConfigurationError(
                "AWSConfig is not set. It is required for invoking tasks."
            )
        return self._aws_config

    @property
    def valkey(self) -> ValkeyConfig:
        """
        Provides access to the Valkey configuration.

        Raises:
            ConfigurationError: If Valkey config was not provided during
                                application initialization.
        """
        if self._valkey_config is None:
            raise ConfigurationError(
                "ValkeyConfig is not set. It is required for state management "
                "and result storage."
            )
        return self._valkey_config
    
    @property
    def default_lambda_function_name(self) -> Optional[str]:
        """
        Provides the default Lambda function name.
        """
        return self._default_lambda_function_name