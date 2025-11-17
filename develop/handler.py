from pylambdatasks import LambdaTasks
app = LambdaTasks(
    task_modules=['tasks'],
    default_lambda_function_name="PyLambdaTasks",
    region_name="us-east-1",
    aws_access_key_id="test",
    aws_secret_access_key="test",
    endpoint_url="http://lambda:8080"
)



@app.init()
async def on_startup():
    print("Lambda function is starting up...")


@app.finish()
async def on_shutdown():
    print("Lambda function is shutting down...")


handler = app.handler