# Mosaic (formerly Hippo) — LinkML runtime for the DataHelix platform
# Multi-stage build: install deps -> slim runtime
#
# The image carries the graphql and postgres extras: the DataHelix
# certification compose runs `mosaic serve --graphql` against Postgres
# (certification/compose/docker-compose.certify.yml).
#
# Filesystem convention: the working directory is /project — bind-mount a
# project directory (mosaic.yaml, schemas/, data/) there and the CLI's
# relative defaults (config auto-discovery, schemas/, data/mosaic.db) all
# resolve inside the mount. Absolute --config/--schema-dir/--db-path flags
# work regardless of the workdir, so existing deployments that mount config
# elsewhere (e.g. the certification stack's /app/hippo.yaml) are unaffected.

FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir --prefix=/install ".[graphql,postgres]"

FROM python:3.12-slim

ARG VERSION=dev
ARG REVISION=unknown

LABEL org.opencontainers.image.title="mosaic" \
      org.opencontainers.image.description="Mosaic (formerly Hippo) — LinkML runtime for the DataHelix platform" \
      org.opencontainers.image.source="https://github.com/BU-Neuromics/mosaic" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}"

RUN groupadd -r mosaic && useradd -r -g mosaic -d /project mosaic \
    && mkdir -p /project && chown -R mosaic:mosaic /project

WORKDIR /project

COPY --from=builder /install /usr/local

USER mosaic

# The CLI default is 8000; this image standardizes on 8001 (matching the
# DataHelix certification compose) via the CMD below.
EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

ENTRYPOINT ["mosaic"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8001"]
