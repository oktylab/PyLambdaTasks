FROM python:3.11-slim-bookworm AS base
WORKDIR /var/task
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH=/var/task

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY develop/requirements.txt .

RUN pip install --no-cache-dir ".[cli]" -r requirements.txt

COPY develop/ .

COPY src/pylambdatasks/ ./pylambdatasks

ENTRYPOINT [ "/usr/local/bin/python", "-m", "awslambdaric" ]
CMD [ "handler.handler" ]
CMD [ "pylambdatasks", "run", "handler.handler", "--reload"]