# Hippo — LinkML runtime for the DataHelix platform
# Multi-stage build: install deps -> slim runtime
#
# The image carries the graphql and postgres extras: the DataHelix
# certification compose runs `hippo serve --graphql` against Postgres
# (certification/compose/docker-compose.certify.yml).

FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir --prefix=/install ".[graphql,postgres]"

FROM python:3.12-slim

ARG VERSION=dev
ARG REVISION=unknown

LABEL org.opencontainers.image.title="hippo" \
      org.opencontainers.image.description="Hippo — LinkML runtime for the DataHelix platform" \
      org.opencontainers.image.source="https://github.com/BU-Neuromics/hippo" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}"

RUN groupadd -r hippo && useradd -r -g hippo -d /app hippo
WORKDIR /app

COPY --from=builder /install /usr/local

# Default data and config directories
RUN mkdir -p /data/hippo-db /app/schemas && chown -R hippo:hippo /data /app

USER hippo

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

ENTRYPOINT ["hippo"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8001"]
