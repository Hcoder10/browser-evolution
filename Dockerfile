FROM python:3.12-slim

# Install system deps for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libx11-xcb1 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python packages
COPY requirements-agent.txt .
RUN pip install --no-cache-dir -r requirements-agent.txt

# Install Playwright browsers
RUN playwright install chromium

# Copy app code
COPY agent_api.py .
COPY scorers.py .
COPY genome.py .
COPY evolution.py .

EXPOSE 8080

CMD ["python", "agent_api.py"]
