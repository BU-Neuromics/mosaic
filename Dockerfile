# Hippo — DataHelix metadata tracking service
# Multi-stage build: install deps -> slim runtime

FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim

LABEL org.opencontainers.image.title="hippo" \
      org.opencontainers.image.description="DataHelix metadata tracking service"

RUN groupadd -r datahelix && useradd -r -g datahelix -d /app datahelix
WORKDIR /app

COPY --from=builder /install /usr/local
COPY src/ ./src/

# Default data and config directories
RUN mkdir -p /data/hippo-db /app/schemas && chown -R datahelix:datahelix /data /app

USER datahelix

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

ENTRYPOINT ["hippo"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8001"]
