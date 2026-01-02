import os, uuid, json, traceback, sys, importlib, logging
from types import SimpleNamespace
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from .app import LambdaTasks
logger = logging.getLogger("pylambdatasks.emulator")

@asynccontextmanager
async def lifespan(app: FastAPI):
    app_string = os.getenv("PYLAMBDATASKS_APP")
    module_str, app_str = app_string.rsplit(':', 1)
    try:
        if '.' not in sys.path:
            sys.path.insert(0, '.')
            
        module = importlib.import_module(module_str)
        importlib.reload(module)
        
        app_instance = getattr(module, app_str)
    except ImportError as e:
        raise ImportError(f"Could not import module '{module_str}'. Please check the path.") from e
    except AttributeError:
        raise ValueError(f"Could not find a variable named '{app_str}' in module '{module_str}'.")

    if not isinstance(app_instance, LambdaTasks):
        raise TypeError(f"The variable '{app_str}' in '{module_str}' is not an instance of LambdaTasks.")
    
    app.state.pylambdatasks_app = app_instance
    print(f"Successfully loaded app from: {app_string}")
    yield 


fastapi_app = FastAPI(title="PyLambdaTasks Local Emulator", lifespan=lifespan)

@fastapi_app.post("/2015-03-31/functions/{function_name}/invocations", response_class=Response)
async def invoke_lambda(function_name: str, request: Request):
    pylambdatasks_app: LambdaTasks = request.app.state.pylambdatasks_app

    try:
        event_payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON in request body."})
    
    request_id = str(uuid.uuid4())
    context = SimpleNamespace(
        function_name=function_name,
        aws_request_id=request_id,
        invoked_function_arn=f"arn:aws:lambda:us-east-1:123456789012:function:{function_name}",
        memory_limit_in_mb="128",
        function_version="$LATEST",
        log_group_name=f"/aws/lambda/{function_name}",
        log_stream_name="2024/01/01/[$LATEST]abcdef123456",
        get_remaining_time_in_millis=lambda: 300000
    )
    
    handler_result = None
    handler_exception = None
    
    original_env = os.environ.copy()
    os.environ.update({
        'AWS_REGION': 'us-east-1',
        'AWS_EXECUTION_ENV': 'AWS_Lambda_python3.11',
        'AWS_LAMBDA_FUNCTION_NAME': context.function_name,
        'AWS_LAMBDA_FUNCTION_MEMORY_SIZE': context.memory_limit_in_mb,
        'AWS_LAMBDA_FUNCTION_VERSION': context.function_version,
        'AWS_LAMBDA_LOG_GROUP_NAME': context.log_group_name,
        'AWS_LAMBDA_LOG_STREAM_NAME': context.log_stream_name,
        '_HANDLER': 'handler.handler',
    })

    try:        
        handler_result = await pylambdatasks_app._handle_async(event=event_payload, context=context)
    except Exception as e:
        logger.error(f"Emulator caught exception in {function_name}")
        handler_exception = e
    finally:
        os.environ.clear()
        os.environ.update(original_env)

    headers = {"x-amz-request-id": request_id}
    invocation_type = request.headers.get("x-amz-invocation-type", "RequestResponse")
    if invocation_type == "Event":
        return Response(status_code=202, headers=headers)
    
    if handler_exception:
        headers["X-Amz-Function-Error"] = "Unhandled"
        error_payload = {
            "errorMessage": str(handler_exception),
            "errorType": type(handler_exception).__name__,
            "stackTrace": traceback.format_exc().splitlines()
        }
        return JSONResponse(status_code=200, content=error_payload, headers=headers)
    
    return JSONResponse(status_code=200, content=handler_result, headers=headers)
