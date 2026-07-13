FROM python:3.12-slim

# curl + ca-certs needed to fetch the onchainos CLI at build time.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the onchainos CLI (verified SHA256 by the official installer) so the
# server can read OKX.AI marketplace data at runtime.
RUN curl -sSL https://raw.githubusercontent.com/okx/onchainos-skills/main/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"
ENV ONCHAINOS_BIN=/root/.local/bin/onchainos

COPY . .

ENV PORT=8000
# Run the mandatory onchainos pre-flight once at boot (version/integrity + workflow
# sync), then serve. `|| true` so a preflight hiccup never blocks the server.
CMD ["sh", "-c", "onchainos preflight --skill-version 4.2.3 > /tmp/preflight.log 2>&1 || true; uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
