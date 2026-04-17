# Python 3.11 is required: farmclickers/utils/run.py hardcodes the `python3.11` binary.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps. tgcrypto needs a C toolchain at build time; dropped after install.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      ca-certificates \
      git \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps first for better layer caching.
COPY requirements.txt ./
RUN pip install --upgrade pip \
 && pip install -r requirements.txt

# Copy the rest of the project.
COPY run_all.py ./
COPY services ./services

# Ensure session/data dirs exist even if the persistent volume is empty on first boot.
RUN mkdir -p services/farmclickers/sessions \
             services/notpixel/sessions \
             services/tomarketod \
 && touch services/tomarketod/data.txt \
          services/tomarketod/proxies.txt

# Railway sets PORT but we are a worker; we simply ignore it.
CMD ["python3.11", "run_all.py"]
