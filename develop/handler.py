from pylambdatasks import LambdaTasks, Task, LambdaContext
import logging
import sys

logging.basicConfig(
    level=logging.INFO, 
    format="[%(name)s] %(levelname)s: %(message)s",
    stream=sys.stdout
)


app = LambdaTasks(
    task_modules=['tasks'],
    default_lambda_function_name="PyLambdaTasks",
    region_name="us-east-1",
    aws_access_key_id="test",
    aws_secret_access_key="test",
    endpoint_url="http://lambda:8080",
    read_timeout=600,
    
)


@app.on_startup()
async def on_startup(self: LambdaTasks, event, context: LambdaContext, task: Task):
    # print(f"on_startup {event}, {context}, {self}, {task}")
    pass

@app.on_shutdown()
async def on_shutdown(self: LambdaTasks, event, context: LambdaContext, task: Task):
    pass
    # print(f"on_shutdown {event}, {context}, {self}, {task}")

@app.before_request()
async def before_request(self: LambdaTasks, event, context: LambdaContext, task: Task):
    print(context.aws_request_id)
    pass
    # print(f"before_request {event}, {context}, {self}, {task}")

@app.after_request()
async def after_request(self: LambdaTasks, event, context: LambdaContext, task: Task):
    pass
    # print(f"after_request {event}, {context}, {self}, {task}")
    

handler = app.handler