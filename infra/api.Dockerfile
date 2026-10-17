# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm@sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89 AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN mkdir -p /var/lib/fortress/media /var/lib/fortress/models \
    && chown -R 10001:10001 /var/lib/fortress

FROM base AS harness
COPY infra/smoke_server.py /opt/fortress-smoke.py
USER 10001:10001
CMD ["python", "/opt/fortress-smoke.py", "serve", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS dependencies
# Immutable Debian archive fixes OS dependency resolution; signatures remain checked.
RUN printf 'deb https://snapshot.debian.org/archive/debian/20261001T000000Z bookworm main\ndeb https://snapshot.debian.org/archive/debian-security/20261001T000000Z bookworm-security main\n' > /etc/apt/sources.list \
    && rm -f /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get -o Acquire::Check-Valid-Until=false install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
RUN printf 'uv==0.13.1 --hash=sha256:696dcf6d807d85da978f4db8472da81dccc1254b18b52cbd1367c4d923c421e0\n' > /tmp/uv-bootstrap.txt \
    && python -m pip install --no-cache-dir --require-hashes -r /tmp/uv-bootstrap.txt \
    && rm /tmp/uv-bootstrap.txt
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --python /usr/local/bin/python
ENV PATH="/app/.venv/bin:${PATH}"

FROM dependencies AS production
COPY backend ./backend
COPY contracts ./contracts
USER 10001:10001
CMD ["sh", "-c", "exec uvicorn \"${FORTRESS_API_APP:?Set verified API module:attribute from accepted A/I}\" --host 0.0.0.0 --port 8000 --no-access-log"]
