################################################################################
#
# PURPOSE:
#
#   This package implements a high-fidelity, Boto3-compatible local emulator
#   for the AWS Lambda service, using only Python's standard library.
#
#   It allows developers to use a single, unmodified Dockerfile for both local
#   testing and production deployment, providing a seamless and professional
#   development experience.
#
# COMPONENTS:
#
#   - server.py: A lightweight web server using `http.server` that listens for
#     and responds to invocation requests from a `boto3` client.
#
#   - runtime.py: The core engine that emulates the AWS Lambda execution
#     environment. It creates a mock context, sets environment variables,
#     invokes the user's handler, and captures the result or exception.
#
#   - main.py: The command-line entrypoint for the emulator. It is responsible
#     for parsing the user's handler path, loading their application, and
#     starting the server.
#
################################################################################

# This file marks the `emulator` directory as a Python package.