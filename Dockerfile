FROM python:3.9-slim

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    chromium-browser \
    xvfb \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo-gobject2 \
    fonts-liberation \
    libx11-xcb1 \
    libxcb-dri3-0 \
    libxss1 \
    libxtst6 \
    xdg-utils \
    libdrm2 \
    libxkbcommon0 \
    libxrandr2 \
    libxfixes3 \
    libcairo2 \
    libasound2 \
    libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser
ENV DISPLAY=:0
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

# Set working directory
WORKDIR /app

# Copy requirement files
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and browsers
RUN pip install playwright && \
    python -m playwright install chromium && \
    python -m playwright install-deps chromium

# Copy the rest of the application
COPY . .

# Command to run the application
CMD ["python", "app.py"]
