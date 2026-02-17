FROM ubuntu:24.04

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY server/. ./
RUN rm -rf .venv

RUN uv sync