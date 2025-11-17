import os, sys, typer
from rich.console import Console

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
def build():
    raise NotImplementedError("The 'build' command is not yet implemented.")

# ==============================================================================
# Main Execution Trigger
# ==============================================================================

if __name__ == "__main__":
    app()