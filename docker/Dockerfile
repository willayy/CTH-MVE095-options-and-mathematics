FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY docker/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

CMD ["python", "src/trading_bot.py", "--host", "ib-gateway", "--port", "4004", "--client-id", "10", "--fixed-capital-amount", "100000.0", "--credibility-percentage", "0.95", "--decay-factor", "0.995", "--check-interval-seconds", "5.0", "SPX:CBOE:USD", "ESTX50:EUREX:EUR"]
