# Use Python 3.11 as base image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies for Tesseract, image processing, and fonts
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-amh \
    tesseract-ocr-eng \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    poppler-utils \
    fonts-noto \
    fonts-dejavu \
    fonts-freefont-ttf \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install additional Amharic language data for better OCR
RUN wget -O /tmp/amh.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/amh.traineddata \
    && mv /tmp/amh.traineddata /usr/share/tesseract-ocr/4.00/tessdata/

# Set Tesseract environment variables
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
