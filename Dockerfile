FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      git \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip \
 && pip install -r requirements.txt

COPY run_all.py ./
COPY services ./services

RUN mkdir -p services/farmclickers \
             services/notpixel \
             services/tomarketod \
 && touch services/farmclickers/data.txt \
          services/notpixel/data.txt \
          services/tomarketod/data.txt \
          services/tomarketod/proxies.txt \
 && echo '{}' > services/tomarketod/tokens.json

CMD ["python3.11", "run_all.py"]
