################################################################################
#
# PURPOSE:
#
#   This module defines the primary command-line interface (CLI) for the
#   PyLambdaTasks framework. It provides two distinct, explicit commands for
#   developers: `run` for local development and `build` for creating production
#   images.
#
# RESPONSIBILITIES:
#
#   1. Implement the `run` command, which is the dedicated entrypoint for local
#      development. It loads the user's application and starts the Boto3-
#      compatible emulator server with optional live-reloading via `watchfiles`.
#
#   2. Implement the `build` command, which orchestrates the `docker build`
#      process to create a production-ready, ECR-compatible Lambda image.
#      It targets a specific stage in the user's Dockerfile and streams the
#      output for clear feedback.
#
# ARCHITECTURE:
#
#   The CLI is architected as a pure orchestration layer, decoupled from the
#   library's core logic. It has no "smart" environment detection. Each command
#   has a single, well-defined responsibility. This separation of concerns
#   ensures the CLI is a simple, maintainable, and predictable interface. `run`
#   delegates to `emulator.main` and `emulator.server`, while `build` delegates
#   to the system's `docker` executable.
#
################################################################################

import os
import sys
import subprocess
from pathlib import Path

import typer
from rich.console import Console
from typing import Optional

try:
    from .emulator.main import load_app_from_handler_path
    from .emulator.server import start_server
except ImportError:
    print("Error: CLI dependencies are not installed. Please run 'pip install pylambdatasks[cli]'")
    sys.exit(1)


# ==============================================================================
# CLI Application Setup
# ==============================================================================

app = typer.Typer(
    name="pylambdatasks",
    help="A CLI for running the local emulator and building production Lambda images.",
    rich_markup_mode="markdown"
)
console = Console()

# ==============================================================================
# `run` Command (For Local Development)
# ==============================================================================
@app.command(help="Starts the local Lambda emulator for development.")
def run(
    handler_path: str = typer.Argument(
        ...,
        help="Path to the handler, e.g., 'myapp.main.handler'",
    ),
    host: str = typer.Option(
        "0.0.0.0", "--host",
        help="Host to bind the emulator server to.",
        envvar="PYLAMBDATASKS_HOST",
        show_envvar=True,
        rich_help_panel="Server Options"
    ),
    port: int = typer.Option(
        8080, "--port",
        help="Port to bind the emulator server to.",
        envvar="PYLAMBDATASKS_PORT",
        show_envvar=True,
        rich_help_panel="Server Options"
    ),
    reload: bool = typer.Option(
        False, "--reload",
        help="Enable auto-reloading on code changes.",
        rich_help_panel="Development Options"
    ),
):
    """
    Starts the local emulator. If --reload is used, it wraps the call
    in `watchfiles` to monitor for changes.
    """
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    if reload:
        command_args = [
            "pylambdatasks", 
            "run", handler_path,
            "--host", host, 
            "--port", str(port)
        ]
        console.print(f"[yellow]Watching for changes in '{os.getcwd()}'...[/yellow]")
        os.execvp(
            "watchfiles",
            ["watchfiles", '--filter', 'python', ' '.join(command_args), "."]
        )
        return

    try:
        app_instance = load_app_from_handler_path(handler_path)
        console.print(f"[green]PyLambdaTasks Emulator running on http://{host}:{port}[/green]")
        start_server(host=host, port=port, app_instance=app_instance)
    except (ValueError, ImportError) as e:
        console.print(f"\n[bold red]Emulator startup failed:[/bold red] {e}")
        raise typer.Exit(code=1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down emulator server.[/yellow]")


# ==============================================================================
# `build` Command (For Production Images)
# ==============================================================================
@app.command(help="Builds a production-ready Docker image for AWS Lambda.")
def build(
    tag: Optional[str] = typer.Option(
        None, "--tag", "-t",
        help="The tag for the Docker image, e.g., 'my-app:latest'",
        rich_help_panel="Image Options"
    ),
    target: Optional[str] = typer.Option(
        None, "--target",
        help="The build target stage in the Dockerfile.",
        rich_help_panel="Image Options"
    ),
    dockerfile: Path = typer.Option(
        "Dockerfile", "--file", "-f",
        help="Path to the Dockerfile.",
        rich_help_panel="Image Options"
    ),
):
    """
    Constructs and executes a `docker build` command, targeting the 'lambda'
    stage by default, to create a production image.
    """
    if not dockerfile.exists():
        console.print(f"[bold red]Error:[/bold red] Dockerfile not found at '{dockerfile}'")
        raise typer.Exit(code=1)

    if tag:
        console.print(f"[cyan]Building Lambda image with tag: [bold]{tag}[/bold][/cyan]")
    else:
        console.print("[cyan]Building Lambda image[/cyan]")

    command = [
        "docker", "build",
        ".",
        "-f", str(dockerfile),
    ]

    if target:
        command.extend(["--target", target])

    if tag:
        command.extend(["-t", tag])

    try:
        process = subprocess.run(
            command, check=True, text=True,
            stdout=sys.stdout, stderr=sys.stderr
        )
        console.print(f"\n[bold green]Image '{tag}' built successfully![/bold green]")

    except FileNotFoundError:
        console.print("[bold red]Error:[/bold red] 'docker' command not found. Is Docker installed and in your PATH?")
        raise typer.Exit(code=1)
    except subprocess.CalledProcessError:
        console.print(f"\n[bold red]Docker build failed.[/bold red]")
        raise typer.Exit(code=1)

# ==============================================================================
# Main Execution Trigger
# ==============================================================================

if __name__ == "__main__":
    app()