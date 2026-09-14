FROM python:3.12-slim

# curl + ca-certs for the Node setup script; Node 22 for the onchainos installer
# (2026-09-14: OKX retired raw.githubusercontent.com/okx/onchainos-skills/main/install.sh,
# the build failed with 404; the supported path is now `npx @okxweb3/onchainos-installer`).
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the onchainos CLI with OKX's npm installer so the server can read OKX.AI
# marketplace data at runtime. Writes /root/.local/bin/onchainos (verified on a clean
# HOME, 14 Sep 2026, CLI 4.6.0).
RUN CI=1 npx -y @okxweb3/onchainos-installer install --stable \
    && /root/.local/bin/onchainos --version
ENV PATH="/root/.local/bin:${PATH}"
ENV ONCHAINOS_BIN=/root/.local/bin/onchainos

COPY . .

ENV PORT=8000
# At boot: pre-flight (version/integrity + workflow sync), then a silent API-Key
# login (reads OKX_API_KEY / OKX_SECRET_KEY / OKX_PASSPHRASE from env) so the
# read-only marketplace calls have a session. `|| true` so neither blocks serving.
# --proxy-headers + --forwarded-allow-ips: Railway terminates TLS and forwards over http,
# so without these uvicorn builds request.url as http:// and the x402 challenge advertises
# an http:// resource URL (verified against prod, Jul 17). A strict x402 client comparing
# the challenge's resource.url to the https:// URL it called can reject the mismatch.
CMD ["sh", "-c", "onchainos wallet login > /tmp/login.log 2>&1 || true; uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
