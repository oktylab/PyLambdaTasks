import os
import typer
import uvicorn
from rich.console import Console

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
# `run` Command
# ==============================================================================
@app.command(help="Starts the local Lambda emulator for development.")
def run(
    app_string: str = typer.Argument(
        ...,
        help="The path to the app instance, e.g., 'handler:app'",
        metavar="MODULE:VARIABLE"
    ),
    host: str = typer.Option("0.0.0.0", "--host", help="Host for the emulator server."),
    port: int = typer.Option(8080, "--port", help="Port for the emulator server."),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reloading on code changes."),
):
    """
    Starts the local emulator.
    """
    os.environ['PYLAMBDATASKS_APP'] = app_string
    uvicorn.run(
        "pylambdatasks.server:fastapi_app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )

# ==============================================================================
# `build` Command (For Production Images)
# ==============================================================================
@app.command(help="Builds a production-ready Docker image for AWS Lambda.")
def build():
    raise NotImplementedError("The 'build' command is not yet implemented.")


if __name__ == "__main__":
    app()