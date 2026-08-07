# api — built from THIS app's own package, never from a shared
# infra Dockerfile: the version floor lives in pyproject.toml, and a build that
# installed it anywhere else would make the declared floor a lie.
#
# ⚠️ This file exists only because api OWNS the code
# (`owns_code: true`). N services can run this ONE image — the identity doors
# are three services over one image — and each of them renders its own wiring
# with its own port and its own sleep answer. So the DNA_API_PORT
# baked in below is a DEFAULT for the image, not the truth about any service:
# the container app and the compose fragment set it per service, and they win.
FROM python:3.12-slim AS base

LABEL org.opencontainers.image.title="api" \
      org.opencontainers.image.description="api — a DNA runtime face"

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DNA_API_HOST=0.0.0.0 \
    DNA_API_PORT=8080

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

EXPOSE 8080

CMD ["api"]
