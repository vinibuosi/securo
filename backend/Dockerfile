# syntax=docker/dockerfile:1
FROM python:3.14-slim

WORKDIR /app

# Install system deps for asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Dependencies come from uv.lock (the source of truth — see scripts/lock.sh).
# The export never touches the lock (--frozen); pip then installs with hash
# checking, so the image only ever contains the exact audited versions. uv is
# removed afterwards — it is a build tool, not a runtime dependency.
# This layer is cached until pyproject.toml or uv.lock change.
COPY pyproject.toml uv.lock ./
# renovate: datasource=pypi depName=uv
RUN --mount=type=secret,id=proxy_ca,target=/run/secrets/proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca SSL_CERT_FILE=/run/secrets/proxy_ca; fi \
    && pip install --no-cache-dir uv==0.13.0 \
    && uv export --frozen --no-emit-project -o /tmp/requirements.txt \
    && pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt \
    && pip uninstall -y uv \
    && rm /tmp/requirements.txt

COPY . .
# The project itself: deps are already satisfied above, so --no-deps keeps
# this layer from re-resolving anything outside the lock.
RUN --mount=type=secret,id=proxy_ca,target=/run/secrets/proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca SSL_CERT_FILE=/run/secrets/proxy_ca; fi \
    && pip install --no-cache-dir --no-deps -e .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
