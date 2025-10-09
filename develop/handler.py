from pylambdatasks import LambdaTasks, AwsConfig, ValkeyConfig
import socket

app = LambdaTasks(
    task_modules=['tasks'],
    default_lambda_function_name="PyLambdaTasks",
    aws_config=AwsConfig(
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        endpoint_url="http://lambda:8080"
    ),
    valkey_config=ValkeyConfig(
        host="valkey",
        port=6379,
        task_key_expire_in_seconds=60,
    )
    # valkey_config=ValkeyConfig(
    #     host="valkey",
    #     port=6379,
    #     task_key_expire_in_seconds=60,
    #     password="password",
    #     username="username",
    #     socket_connect_timeout=10,
    #     socket_keepalive=True,
    #     socket_keepalive_options={
    #         socket.TCP_KEEPIDLE: 60,
    #         socket.TCP_KEEPINTVL: 30,
    #         socket.TCP_KEEPCNT: 5,
    #     },
    #     ssl=True,
    #     ssl_cert_reqs=None, 
    # )
)
handler = app.handler