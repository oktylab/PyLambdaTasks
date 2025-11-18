# PyLambdaTasks

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Built with](https://img.shields.io/badge/Built%20with-AWS%20Lambda-FF9900?logo=amazonaws)](https://aws.amazon.com/lambda/)
[![Powered by](https://img.shields.io/badge/Powered%20by-Boto3-232F3E?logo=boto3)](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)

**A Pythonic, Celery-like framework for building, testing, and deploying task queues on AWS Lambda.**

PyLambdaTasks simplifies AWS Lambda development by letting you package multiple, independent tasks into a single container image. It combines the developer ergonomics of frameworks like Celery and FastAPI with a high-fidelity local emulator, enabling a seamless development-to-production workflow.

---

### Core Pillars

*   **Celery-like Simplicity:** Define tasks with a simple `@app.task` decorator and invoke them remotely with `.invoke()` or `.delay()`.
*   **Unified Deployment:** Package an entire suite of tasks into one Lambda function, reducing deployment complexity and cold starts.
*   **High-Fidelity Local Emulator:** A built-in, Boto3-compatible server lets you run and test your entire Lambda function locally.
*   **FastAPI-Style Dependency Injection:** Manage resources like database connections or user context with a powerful, clean DI system (`Depends`).
*   **Powerful CLI:** A dedicated command-line interface to run the local emulator with live-reloading.

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

Create your task functions in `tasks.py`. The `@app.task` decorator registers them. You can use `Depends` to inject dependencies like configuration or database connections.

```python
# tasks.py
from typing import Annotated, Dict, Any
from handler import app  # Import the app instance from your handler file
from pylambdatasks import Depends

# 1. Define a dependency (e.g., a function to get user context)
def get_user_context() -> Dict[str, str]:
    """A simple dependency providing a mock user context."""
    return {"user_id": "user-123", "role": "admin"}

# 2. Create a type alias for the dependency
UserContext = Annotated[Dict[str, str], Depends(get_user_context)]

@app.task(name="ADD_NUMBERS")
async def add_numbers(a: int, b: int) -> Dict:
    """A simple task that adds two numbers."""
    print(f"Executing ADD_NUMBERS: {a} + {b}")
    return {"result": a + b}

@app.task(name="PROCESS_DATA")
async def process_data(data: Dict[str, Any], context: UserContext) -> Dict:
    """
    A task that processes data and uses an injected dependency.
    The 'context' argument will be automatically resolved and provided.
    """
    print(f"Executing PROCESS_DATA for user: {context['user_id']}")
    processed_data = {key.upper(): value for key, value in data.items()}
    return {"processed_data": processed_data}
```

### 3. Configure the Application (`handler.py`)

This file is the heart of your Lambda function. You instantiate `LambdaTasks` and expose the handler.

```python
# handler.py
from pylambdatasks import LambdaTasks

app = LambdaTasks(
    # A list of modules where your @app.task-decorated functions live.
    task_modules=['tasks'],

    # The default AWS Lambda function name tasks will be invoked against.
    default_lambda_function_name="PyLambdaTasks-Local",

    # Boto3 client configuration.
    region_name="us-east-1",
    aws_access_key_id="test",
    aws_secret_access_key="test",

    # For local development, this URL points to our emulator.
    # Boto3 will automatically connect to it instead of AWS.
    endpoint_url="http://lambda:8080"
)

# This is the handler entrypoint that the emulator (and AWS Lambda) will use.
handler = app.handler
```

### 4. Run the Local Emulator

With your tasks and handler defined, start the local emulator from your terminal using the `pylambdatasks` CLI.

```bash
# This command tells the CLI to:
# 1. Look for the `app` object inside the `handler.py` module.
# 2. Start the emulator server.
# 3. Watch for file changes and reload automatically.
pylambdatasks run handler:app --reload
```

You will see output confirming the server is running and ready to accept Boto3 requests.

### 5. Invoke Tasks (`client.py`)

From a separate process (like a web API or another script), you can invoke your tasks. The task objects (`add_numbers`, `process_data`) now have `.invoke()` and `.delay()` methods that trigger a Lambda invocation behind the scenes.

```python
# client.py
import asyncio
from tasks import add_numbers, process_data

async def main():
    print("Invoking 'ADD_NUMBERS' task synchronously...")
    # .invoke() calls the Lambda, waits for the result, and returns it.
    sync_result = await add_numbers.invoke(a=10, b=5)
    print(f"  -> Result: {sync_result}")

    print("\nInvoking 'PROCESS_DATA' task synchronously...")
    # .delay() is for "fire-and-forget" asynchronous invocation.
    await process_data.delay(data={"message": "hello world"})
    print("  -> 'PROCESS_DATA' task dispatched.")

if __name__ == "__main__":
    asyncio.run(main())
```

Run the client in a new terminal:
```bash
python client.py
```

You'll see the results printed in your client terminal and the execution logs (`Executing ADD_NUMBERS...`) in your emulator terminal.

---

## Docker & AWS Lambda

The strategy is to build a single, production-ready Docker image that can be switched into "development mode" using a `docker-compose.yml` override.

### The Production `Dockerfile`

A production image for AWS Lambda requires an entrypoint that uses the official AWS Runtime Interface Client (`awslambdaric`).

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
# THIS IS REQUIRED FOR THE IMAGE TO RUN IN AWS LAMBDA.
ENTRYPOINT [ "/usr/local/bin/python", "-m", "awslambdaric" ]

# The CMD specifies the handler that awslambdaric should run.
CMD [ "handler.handler" ]
```

### Development with Docker Compose

When running locally, we override the production `ENTRYPOINT` and `CMD` to run our local emulator instead. This is the key to a seamless workflow: **one image, two modes.**

```yaml
# compose.yml
services:
  # This service runs our Lambda code in emulator mode
  lambda:
    build: . # Build the production Dockerfile
    container_name: pylambdatasks-lambda
    volumes:
      - .:/var/task # Mount code for live-reloading
    ports:
      - "8080:8080" # Expose the emulator port

    # --- DEVELOPMENT OVERRIDE ---
    # We discard the production ENTRYPOINT and CMD from the Dockerfile
    # and replace them with our local emulator command.
    entrypoint: "" # Clear the production entrypoint
    command:
      - pylambdatasks
      - run
      - handler:app   # The app instance to run
      - --reload      # Enable live-reloading
      - --host
      - 0.0.0.0
      - --port
      - "8080"
```

With this setup, `docker compose up` will use your production image for local development. When you're ready to deploy, push the exact same image to AWS ECR, and it will work correctly in Lambda.

## Lifecycle Hooks

You can register functions to run at different stages of the Lambda lifecycle.

- `@app.on_startup()` — Runs only once on cold-start. Ideal for setting up database connection pools.
- `@app.on_shutdown()` — Runs when the Lambda container is about to be shut down.
- `@app.before_request()` — Runs before every single invocation.
- `@app.after_request()` — Runs after every single invocation, even if it failed.

Example (`handler.py`):
```python
# ... app = LambdaTasks(...)

@app.on_startup()
async def setup_connections():
    print("Cold Start: Creating DB pool...")

@app.on_shutdown()
async def close_connections():
    print("Shutdown: Closing DB pool...")

@app.before_request()
async def log_invocation_start():
    print("-> Invocation started.")

handler = app.handler
```

## CLI Reference

#### `pylambdatasks run [OPTIONS] APP_PATH`

Starts the local Lambda emulator.

*   **`APP_PATH`**: Path to your app instance in `MODULE:VARIABLE` format (e.g., `handler:app`).
*   **`--host TEXT`**: Host to bind to. Defaults to `0.0.0.0`.
*   **`--port INTEGER`**: Port to bind to. Defaults to `8080`.
*   **`--reload`**: Enable auto-reloading on code changes.

## License

This project is licensed under the GNU General Public License v3.0.

---

## Roadmap

- [ ] **Custom Logging:** Provide hooks or a configurable system to integrate with custom logging solutions and structured log formats.
- [ ] **AIOBoto3 Support:** Offer native integration with `aioboto3` for a fully asynchronous AWS client experience.
- [ ] **UI for Task Monitoring:** Develop a simple web-based user interface to visualize task invocations and monitor the system locally.
- [ ] **Batching and SQS Integration:** Add native support for SQS triggers and batch processing of tasks.