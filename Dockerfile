FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system deps for Playwright and SQLite
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        gcc \
        libnss3 \
        libatk-bridge2.0-0 \
        libdrm2 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libgbm1 \
        libasound2 \
        libpango-1.0-0 \
        libcairo2 \
        libatspi2.0-0 \
        libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml setup.py ./
RUN pip install --no-cache-dir -e ".[dev]"

# Install Playwright browsers
RUN playwright install chromium

COPY . .

EXPOSE 8000

CMD ["uvicorn", "agentic_computer.server.app:app", "--host", "0.0.0.0", "--port", "8000"]
