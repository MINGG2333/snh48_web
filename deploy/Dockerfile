# ═══════════════════════════════════════════════════════════════════════════
# SNH48 演艺信息站 - Dockerfile
# ═══════════════════════════════════════════════════════════════════════════

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY website/requirements.txt ./website/requirements.txt
COPY transcript_analyze/requirements_kb_qa.txt ./transcript_analyze/requirements_kb_qa.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r website/requirements.txt && \
    pip install --no-cache-dir -r transcript_analyze/requirements_kb_qa.txt

# Copy the rest of the application
COPY website/ ./website/
COPY transcript_analyze/ ./transcript_analyze/

# Create necessary directories
RUN mkdir -p video_knowledge_db

# Expose port
EXPOSE 8000

# Run the application
CMD ["python", "-m", "website.main"]
