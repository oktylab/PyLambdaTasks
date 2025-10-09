################################################################################
#
# PURPOSE:
#
#   This module implements the Boto3-compatible HTTP server using the `aiohttp`
#   library. It listens for invocation requests, parses them according to the
#   AWS Lambda Data Plane API specification, delegates the actual execution to
#   the `runtime` module, and formats a compliant HTTP response. This version
#   replaces the standard library's `http.server` to provide a native async
#   environment, solving event loop conflicts.
#
# RESPONSIBILITIES:
#
#   1. Implement an `aiohttp` request handler to process incoming POST requests.
#
#   2. Validate and parse the request path to extract the `function_name`,
#      conforming to the `/2015-03-31/functions/{...}/invocations` structure.
#
#   3. Read and interpret critical headers, specifically `x-amz-invocation-type`.
#
#   4. Read and deserialize the JSON event payload from the request body.
#
#   5. Delegate the processed request data (payload, invocation type, etc.) to
#      the `run_emulated_invocation` function in the `runtime` module.
#
#   6. Receive a result object from the `runtime` and meticulously construct a
#      Boto3-compatible `aiohttp.web.Response`, including the correct status
#      code, headers, and serialized body.
#
#   7. Provide a `start_server` function that initializes and runs the `aiohttp`
#      application, injecting the user's `LambdaTasks` app instance into it.
#
# ARCHITECTURE:
#
#   This server is designed as a thin, stateless protocol layer built on the
#   natively asynchronous `aiohttp` framework. This is a critical architectural
#   choice that ensures a single, long-running asyncio event loop is used for
#   the entire lifetime of the server. This prevents the "Event loop is closed"
#   errors that occur when mixing synchronous servers with async client libraries.
#
#   Dependency injection is handled by the `aiohttp.web.Application` object
#   itself. The `start_server` function creates the application and stores a
#   reference to the user's `LambdaTasks` instance in the application's context
#   (e.g., `app['pylambdatasks_app']`). The request handler function can then
#   access this shared instance via `request.app`, ensuring a clean, decoupled
#   way to provide context to each request.
#
################################################################################

import json
from aiohttp import web

from .runtime import run_emulated_invocation
from ..app import LambdaTasks

# ==============================================================================
# HTTP Request Handler
# ==============================================================================

async def lambda_invocation_handler(request: web.Request) -> web.Response:
    """
    Handles a single HTTP request to the Lambda emulator's invocation endpoint.
    """
    function_name = request.match_info.get("function_name")
    if not function_name:
        # This case should ideally not be hit if routing is set up correctly.
        return web.Response(status=404, text="Not Found")

    app_instance = request.app.get("pylambdatasks_app")
    if not app_instance:
        error_body = json.dumps({"error": "Emulator handler not configured with an app."})
        return web.Response(status=500, body=error_body, content_type="application/json")

    try:
        # --- Parse the incoming Boto3 request ---
        invocation_type = request.headers.get("x-amz-invocation-type", "RequestResponse")
        event_payload = await request.json()

        # --- Delegate to the runtime emulator ---
        emulation_result = await run_emulated_invocation(
            app=app_instance,
            function_name=function_name,
            invocation_type=invocation_type,
            event_payload=event_payload
        )
        
        # --- Construct and send the Boto3-compatible response ---
        return web.Response(
            status=emulation_result.status_code,
            headers=emulation_result.headers,
            body=emulation_result.body,
            content_type="application/json"
        )

    except json.JSONDecodeError:
        error_body = json.dumps({"error": "Invalid JSON in request body."})
        return web.Response(status=400, body=error_body, content_type="application/json")
    except Exception:
        # A catch-all for any unexpected server errors.
        error_body = json.dumps({"error": "Internal emulator error."})
        return web.Response(status=500, body=error_body, content_type="application/json")


# ==============================================================================
# Server Startup Logic
# ==============================================================================

def start_server(host: str, port: int, app_instance: LambdaTasks):
    """
    Configures and starts the Lambda emulator aiohttp server.

    Args:
        host: The hostname to bind to (e.g., '127.0.0.1').
        port: The port to listen on (e.g., 9000).
        app_instance: The user's configured LambdaTasks application instance.
    """
    # 1. Create the main application object.
    app = web.Application()

    # 2. Inject the user's app instance into the aiohttp application context
    #    so the handler can access it.
    app["pylambdatasks_app"] = app_instance

    # 3. Register the handler for the Boto3-compatible invocation URL.
    #    The {function_name} part is a dynamic segment.
    app.router.add_post(
        "/2015-03-31/functions/{function_name}/invocations",
        lambda_invocation_handler
    )

    # 4. Run the application. This call is blocking and will start the server's
    #    event loop. The `print=None` argument suppresses the default aiohttp
    #    startup banner, allowing our own messages in `main.py` to be clearer.
    web.run_app(
        app,
        host=host,
        port=port,
        print=None
    )