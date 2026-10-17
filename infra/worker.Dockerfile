# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm@sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89 AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN mkdir -p /var/lib/fortress/media /var/lib/fortress/models \
    && chown -R 10001:10001 /var/lib/fortress

FROM base AS harness
COPY infra/smoke_server.py /opt/fortress-smoke.py
USER 10001:10001
CMD ["python", "/opt/fortress-smoke.py", "worker"]

FROM base AS dependencies
RUN printf 'deb https://snapshot.debian.org/archive/debian/20261001T000000Z bookworm main\ndeb https://snapshot.debian.org/archive/debian-security/20261001T000000Z bookworm-security main\n' > /etc/apt/sources.list \
    && rm -f /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get -o Acquire::Check-Valid-Until=false install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
RUN printf 'uv==0.13.1 --hash=sha256:696dcf6d807d85da978f4db8472da81dccc1254b18b52cbd1367c4d923c421e0\n' > /tmp/uv-bootstrap.txt \
    && python -m pip install --no-cache-dir --require-hashes -r /tmp/uv-bootstrap.txt \
    && rm /tmp/uv-bootstrap.txt
COPY pyproject.toml uv.lock ./
# K currently pins CPU Torch wheels. CUDA readiness remains blocked until K's owner
# supplies a compatible verified GPU lock; do not silently fork that shared lock.
RUN uv sync --locked --no-dev --extra ml --python /usr/local/bin/python
ENV PATH="/app/.venv/bin:${PATH}" PIP_NO_INDEX=1 HF_HUB_OFFLINE=1

FROM dependencies AS production
COPY backend ./backend
COPY contracts ./contracts
COPY rules ./rules
COPY ml ./ml
USER 10001:10001
CMD ["sh", "-c", "exec celery -A \"${FORTRESS_WORKER_APP:?Set verified Celery module:attribute from accepted A/I}\" worker --concurrency=1 --prefetch-multiplier=1 --pool=prefork --soft-time-limit=239 --time-limit=240 --pidfile=/tmp/fortress-worker.pid --loglevel=WARNING"]
