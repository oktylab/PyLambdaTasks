# PyLambdaTasks

<!-- [![PyPI Version](https://img.shields.io/pypi/v/pylambdatasks.svg)](https://pypi.org/project/pylambdatasks/) -->
<!-- [![Python Versions](https://img.shields.io/pypi/pyversions/pylambdatasks.svg)](https://pypi.org/project/pylambdatasks/) -->
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Built with](https://img.shields.io/badge/Built%20with-AWS%20Lambda-FF9900?logo=amazonaws)](https://aws.amazon.com/lambda/)
[![Uses](https://img.shields.io/badge/Uses-Valkey-e02b37?logo=redis)](https://valkey.io/)
[![Powered by](https://img.shields.io/badge/Powered%20by-Boto3-232F3E?logo=boto3)](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)

**A Pythonic, Celery-like framework for building, testing, and deploying task queues on AWS Lambda.**

PyLambdaTasks simplifies AWS Lambda development by letting you package multiple, independent tasks into a single container image. It combines the developer ergonomics of frameworks like Celery and FastAPI with a high-fidelity local emulator, enabling a seamless development-to-production workflow.

---

### Core Pillars

*   **Celery-like Simplicity:** Define tasks with a simple `@app.task` decorator.
*   **Unified Deployment:** Package an entire suite of tasks into one Lambda function, reducing deployment complexity and cold starts.
*   **High-Fidelity Local Emulator:** A built-in, Boto3-compatible server lets you run and test your Lambda function locally.
*   **Valkey/Redis State Tracking:** Automatically track task status (`PROGRESS`, `SUCCESS`, `FAILED`), arguments, and results in a state backend.
*   **FastAPI-Style Dependency Injection:** Manage resources like database connections with a powerful, clean DI system (`Depends`).
*   **Powerful CLI:** A dedicated command-line interface to run the local emulator with live-reloading and build production-ready images.

## Installation

Install the library and its CLI dependencies from PyPI.

```bash
pip install "pylambdatasks[cli]"
```

## Quick Start: Local-First Development

This guide demonstrates how to build and run a complete task system on your local machine.

### 1. Project Structure

Create a new project with the following structure:

```
my_lambda_project/
├── handler.py
├── tasks.py
└── client.py
```

### 2. Define Your Tasks (`tasks.py`)

Create your task functions in `tasks.py`. The `@app.task` decorator registers them. The `self: StateManager` argument is automatically injected by the framework, giving you access to the state-tracking API.

```python
# tasks.py
from typing import Dict
from pylambdatasks.state import StateManager
from handler import app  # Import the app instance from your handler file

@app.task(name="ADD_NUMBERS")
async def add_numbers(self: StateManager, a: int, b: int) -> Dict:
    """A simple task that adds two numbers."""
    print(f"Executing ADD_NUMBERS: {a} + {b}")
    result = a + b
    # Optionally update the task's record in Valkey with custom metadata
    await self.update_metadata({"processed_by": "local-worker-1"})
    return {"result": result}

@app.task(name="PROCESS_TEXT")
async def process_text(self: StateManager, text: str) -> Dict:
    """A simple task that processes a string."""
    print(f"Executing PROCESS_TEXT on: {text}")
    return {"processed_text": text.upper()}
```

### 3. Configure the Application (`handler.py`)

This file is the heart of your configuration. You instantiate `LambdaTasks`, connect it to your tasks, and configure AWS and Valkey clients.

```python
# handler.py
from pylambdatasks import LambdaTasks, AwsConfig, ValkeyConfig

app = LambdaTasks(
    # A list of modules where your @app.task-decorated functions live.
    task_modules=['tasks'],

    # The default AWS Lambda function name tasks will be invoked against.
    default_lambda_function_name="PyLambdaTasks",

    # Boto3 client configuration.
    aws_config=AwsConfig(
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        # For local development, this URL points to our emulator.
        # Boto3 will automatically connect to it instead of AWS.
        endpoint_url="http://127.0.0.1:8080"
    ),

    # Valkey/Redis client configuration for the state backend.
    # Assumes a local Valkey/Redis server is running.
    valkey_config=ValkeyConfig(
        host="127.0.0.1",
        port=6379,
    )
)

# This is the handler entrypoint that the emulator (and AWS Lambda) will use.
handler = app.handler
```

### 4. Run the Local Emulator

With your tasks and handler defined, start the local emulator from your terminal using the `pylambdatasks` CLI. You'll need a local Valkey/Redis instance running for state management.

```bash
# This command tells the CLI to:
# 1. Look for the `handler` object inside `handler.py`.
# 2. Start the emulator server.
# 3. Watch for file changes and reload automatically.
pylambdatasks run handler.handler --reload
```

You will see the following output, confirming the server is running:

```
Watching for changes in '/path/to/my_lambda_project'...
PyLambdaTasks Emulator running on http://0.0.0.0:8080
Boto3 Endpoint URL: http://0.0.0.0:8080
```

Your Boto3-compatible Lambda is now live at `http://127.0.0.1:8080`.

### 5. Invoke Tasks (`client.py`)

Now, from a separate terminal, you can invoke your tasks using the library's client-side API. The task objects (`add_numbers`, `process_text`) now have `.invoke()` and `.delay()` methods.

```python
# client.py
import asyncio
from tasks import add_numbers, process_text

async def main():
    print("Invoking 'ADD_NUMBERS' task synchronously...")
    # .invoke() calls the Lambda and waits for the result.
    sync_result = await add_numbers.invoke(a=10, b=5)
    print(f"  -> Result: {sync_result}")

    print("\nInvoking 'PROCESS_TEXT' task synchronously...")
    text_result = await process_text.invoke(text="hello world")
    print(f"  -> Result: {text_result}")

if __name__ == "__main__":
    asyncio.run(main())
```

Run the client:

```bash
python client.py
```

You'll see the results printed in your client terminal and the execution logs (`Executing ADD_NUMBERS...`) in your emulator terminal.

---

## Docker & AWS Lambda

The local emulator provides a high-fidelity environment, but the end goal is to run in AWS Lambda. The strategy is to build a single, production-ready Docker image that can be switched into "development mode" using a `docker-compose.yml` override.

### The Production `Dockerfile`

A production image for AWS Lambda requires a specific entrypoint that uses the official AWS Runtime Interface Client (`awslambdaric`). This allows AWS to manage the container's lifecycle.

```dockerfile
# Dockerfile
FROM python:3.11-slim-bookworm

WORKDIR /var/task
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install project dependencies
COPY requirements.txt .
# Ensure pylambdatasks is listed in your requirements.txt
RUN pip install --no-cache-dir "pylambdatasks[cli]" -r requirements.txt

# Copy application code
COPY . .

# This is the official AWS entrypoint for custom Python runtimes.
# It starts the awslambdaric, which will then load and run your handler.
# THIS IS REQUIRED FOR THE IMAGE TO RUN IN AWS LAMBDA.
ENTRYPOINT [ "/usr/local/bin/python", "-m", "awslambdaric" ]

# The CMD specifies the handler that awslambdaric should run.
CMD [ "handler.handler" ]
```

### Development with Docker Compose

When running locally, we don't want to use `awslambdaric`. Instead, we want to run our `pylambdatasks run` command. We can achieve this by building the production-ready image and simply overriding its `ENTRYPOINT` and `CMD` in `docker-compose.yml`.

This is the key to a seamless workflow: **one image, two modes.**

```yaml
# compose.yml
services:
  valkey:
    image: valkey/valkey:7.2-alpine
    ports:
      - "6379:6379"

  # This service runs our Lambda code
  lambda:
    build: . # Build the production Dockerfile
    volumes:
      - .:/var/task # Mount code for live-reloading
    depends_on:
      - valkey

    # --- DEVELOPMENT OVERRIDE ---
    # The magic happens here. We discard the production ENTRYPOINT and CMD
    # from the Dockerfile and replace them with our local emulator command.
    entrypoint: "" # Clear the production entrypoint
    command:
      - pylambdatasks
      - run
      - handler.handler # The handler to run
      - --reload        # Enable live-reloading
      - --host
      - 0.0.0.0
      - --port
      - "8080"
    ports:
      - "8080:8080" # Expose the emulator port
```

With this setup, `docker-compose up` will use your production image for local development. When you're ready to deploy, you can push the exact same image to AWS ECR, and it will work correctly because AWS will use the original `ENTRYPOINT` defined in the `Dockerfile`.




## Lifecycle hooks: init() and finish()

You can register async startup and shutdown hooks on your app instance:

- @app.init() — runs once on cold-start inside the handler's async loop (await async work)
- @app.finish() — attempted on process exit; async hooks are awaited in a short-lived loop in a background thread

Example (handler.py):

```python
from pylambdatasks import LambdaTasks, AwsConfig, ValkeyConfig

app = LambdaTasks(
    task_modules=['tasks'],
    default_lambda_function_name="PyLambdaTasks",
    aws_config=AwsConfig(...),
    valkey_config=ValkeyConfig(...),
)

@app.init()
async def on_startup():
    # async connection/pool creation, warmups, etc.
    print("startup: creating DB pool / connections")
    # await db.connect()

@app.finish()
async def on_shutdown():
    # close connections, flush metrics
    print("shutdown: closing DB pool / connections")
    # await db.close()

handler = app.handler
```

Testing locally
1. Start emulator: pylambdatasks run handler.handler --reload
2. Make a first invocation (e.g., call a task). You should see the `on_startup` output printed during the first invocation.
3. Stop the process/container; you should see `on_shutdown` attempted on exit (may be subject to short timeout).

Notes
- Hooks may be sync or async; prefer async for non-blocking behavior.
- Keep init quick to avoid delaying the first invocation excessively.
- Finish runs in a background thread with a short join timeout — do not rely on long-running teardown there.

## CLI Reference

#### `pylambdatasks run [OPTIONS] HANDLER_PATH`

Starts the local Lambda emulator.

*   **`HANDLER_PATH`**: Path to your handler instance (e.g., `handler.handler`).
*   **`--host TEXT`**: Host to bind to. Defaults to `0.0.0.0`.
*   **`--port INTEGER`**: Port to bind to. Defaults to `8080`.
*   **`--reload`**: Enable auto-reloading on code changes.

#### `pylambdatasks build [OPTIONS]`

Builds a production Docker image. This is a thin wrapper around `docker build`.

*   **`-t, --tag TEXT`**: The tag for the Docker image (e.g., `my-app:latest`).
*   **`-f, --file PATH`**: Path to the Dockerfile. Defaults to `Dockerfile`.
*   **`--target TEXT`**: The build target stage in the Dockerfile.

## License

This project is licensed under the GNU General Public License v3.0.

---

## Roadmap

Here are some of the features and improvements planned for future releases:

- [ ] **Usage without Valkey:** 
  Introduce a "fire-and-forget" mode or support for alternative, lightweight state backends for users who don't need persistent state tracking.
- [ ] **Custom Logging:** 
  Provide hooks or a configurable system to integrate with custom logging solutions and structured log formats.
- [ ] **AIOBoto3 Support:** 
  Offer native integration with `aioboto3` for a fully asynchronous AWS client experience, improving performance for I/O-bound tasks.
- [ ] **UI for Task Tracking:** 
  Develop a simple web-based user interface to visualize task queues, inspect results, and monitor the system.
