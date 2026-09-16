# CloudCtl control-api staging image (D10).
# Build context must be the repository root:
#   docker build -f infra/compose/staging/Dockerfile --build-arg BUILD_SHA=$(git rev-parse --short HEAD) .
# The uv workspace installs all Python members (domain, observability, api, ...)
# from the frozen lockfile so the image matches what CI/local tests exercise.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build

ARG BUILD_SHA=unknown

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# Lockfile-first layers for cache hits.
COPY pyproject.toml uv.lock ./
COPY packages/ ./packages/
COPY services/ ./services/

RUN uv sync --frozen --no-dev

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ARG BUILD_SHA=unknown
LABEL org.opencontainers.image.title="cloudctl-control-api-staging" \
      org.opencontainers.image.description="CloudCtl control API staging build (fleet D10)" \
      org.opencontainers.image.revision="${BUILD_SHA}"

WORKDIR /app
COPY --from=build /app/.venv/ ./venv/
COPY --from=build /app/packages/ ./packages/
COPY --from=build /app/services/ ./services/

# Consumed by the app once the /health/ready build-identity wiring lands
# (service code is out of D10 scope; see docs/runbooks/fleet-deploy.md).
ENV BUILD_SHA=${BUILD_SHA} \
    PATH="/app/venv/bin:${PATH}" \
    PYTHONPATH=/app/services/control-api/src:/app/packages/domain/src:/app/packages/observability/src \
    PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "cloudctl_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
