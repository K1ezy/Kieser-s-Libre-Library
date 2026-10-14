FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system build dependencies for llama-cpp-python and PyMuPDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Pre-download the offline SentenceTransformer embedding model into /app/models/all-MiniLM-L6-v2
RUN python download_model.py

EXPOSE 8080

CMD ["python", "main.py"]
