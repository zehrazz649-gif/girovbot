FROM python:3.11-slim

WORKDIR /app

# Playwright üçün lazım olan sistem kitabxanaları
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    gnupg \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxrandr2 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libgbm1 \
    libpango-1.0-0 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Chromium brauzerini quraşdır
RUN playwright install chromium

COPY bot.py .

CMD ["python", "bot.py"]

