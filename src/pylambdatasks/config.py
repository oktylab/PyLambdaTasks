from typing import Dict, Optional, Any

class Settings:
    def __init__(
        self,
        *,
        default_lambda_function_name: str,
        region_name: str,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        connect_timeout: Optional[int] = None,
        read_timeout: Optional[int] = None,
        total_max_attempts: Optional[int] = None,
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
        config = {}
        
        if self.connect_timeout is not None:
            config["connect_timeout"] = self.connect_timeout

        if self.read_timeout is not None:
            config["read_timeout"] = self.read_timeout
            
        retries = {}
        if self.total_max_attempts is not None:
            retries['total_max_attempts'] = self.total_max_attempts
            retries['mode'] = 'standard'
            
        if retries:
            config["retries"] = retries
            
        return config