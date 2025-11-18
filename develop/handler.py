from pylambdatasks import LambdaTasks
app = LambdaTasks(
    task_modules=['tasks'],
    default_lambda_function_name="PyLambdaTasks",
    region_name="us-east-1",
    aws_access_key_id="test",
    aws_secret_access_key="test",
    endpoint_url="http://lambda:8080"
)


@app.on_startup()
async def on_startup():
    print("✅ (Cold Start) Lambda function is starting up...")

@app.on_shutdown()
async def on_shutdown():
    print("❌ (Container Shutdown) Lambda function is shutting down...")

@app.before_request()
async def before_request():
    print("-> Invocation started.")

@app.after_request()
async def after_request():
    print("<- Invocation finished.")

    

handler = app.handler