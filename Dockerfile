# Use Python 3.11 as base image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies for Tesseract and image processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-amh \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    poppler-utils \
    fonts-noto-cjk \
    fonts-dejavu-core \
    fonts-freefont-ttf \
    wget \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Tesseract Amharic language data directly
RUN mkdir -p /usr/share/tesseract-ocr/4.00/tessdata/ \
    && wget -q -O /usr/share/tesseract-ocr/4.00/tessdata/amh.traineddata \
    https://github.com/tesseract-ocr/tessdata_best/raw/main/amh.traineddata \
    && wget -q -O /usr/share/tesseract-ocr/4.00/tessdata/eng.traineddata \
    https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata

# Set Tesseract environment variable
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata/

# Set working directory
WORKDIR /app

# Copy requirements first (better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create temporary directory for image processing
RUN mkdir -p tmp

# Create a non-root user for security
RUN useradd -m -u 1000 telegrambot \
    && chown -R telegrambot:telegrambot /app
USER telegrambot

# Run the bot
CMD ["python", "bot.py"]
