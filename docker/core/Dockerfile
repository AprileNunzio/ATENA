FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app \
    ATENA_PORT=8443

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY server/requirements.txt server/requirements.txt
RUN pip install -r server/requirements.txt

COPY server ./server

ARG ATENA_SRC_HASH=dev
LABEL org.atena.src=$ATENA_SRC_HASH

EXPOSE 8443
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=4 \
    CMD curl -fsS "http://127.0.0.1:${ATENA_PORT}/health" || exit 1

CMD ["python", "-m", "server.cmd.main"]
