from typing import Dict, Optional, Any

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
        region_name: str,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        connect_timeout: int = 10,
        read_timeout: int = 60,
        total_max_attempts: int = 5,
    ):
        self.default_lambda_function_name = default_lambda_function_name
        self.region_name = region_name
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.endpoint_url = endpoint_url
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.total_max_attempts = total_max_attempts
        

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