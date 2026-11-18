FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN git clone --depth 1 https://github.com/willayy/CTH-MVE095-options-and-mathematics.git /app \
    && pip install --no-cache-dir -r /app/docker/requirements.txt

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "src/trading_bot.py", "--host", "ib-gateway", "--port", "4002", "--client-id", "10", "--fixed-capital-amount", "10000.0", "--credibility-percentage", "0.95", "--decay-factor", "0.995", "--check-interval-seconds", "5.0", "SPX", "CBOE", "USD"]
