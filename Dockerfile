FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends gcc python3-dev && pip install --no-cache-dir -r requirements.txt && apt-get purge -y gcc python3-dev && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY bot/ ./bot/

# Create data directory
RUN mkdir -p /app/data

# Run as non-root user for security
RUN useradd -m botuser && chown -R botuser:botuser /app
USER botuser

CMD ["python", "-m", "bot.main"]
