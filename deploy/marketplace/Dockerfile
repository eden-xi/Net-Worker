# Net-Worker MARKETPLACE container: the login wall + Employee / Manager dashboards.
# Same as deploy/Dockerfile, plus the marketplace/ folder, and it starts marketplace.server.
#
# Build from the REPO ROOT:  docker build -f deploy/marketplace/Dockerfile .
# On Render: Dockerfile Path = ./deploy/marketplace/Dockerfile, Build Context = .
# To go back to the original site, point Render at ./deploy/Dockerfile again.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    PORT=8000

WORKDIR /app

COPY deploy/requirements.txt deploy/requirements.txt
RUN pip install --no-cache-dir -r deploy/requirements.txt

# Code only, file by file. The real database (backend/database/*.db) and
# resumes (uploads/) are never copied, so they can't end up in the image.
COPY backend/api/*.py backend/api/
COPY backend/database/database.py backend/database/
COPY frontend/ frontend/
COPY deploy/*.py deploy/*.csv deploy/
COPY marketplace/*.py marketplace/
COPY marketplace/frontend/ marketplace/frontend/

RUN useradd --create-home appuser \
    && mkdir -p /data \
    && chown -R appuser /app /data
USER appuser

EXPOSE 8000

# Render sets $PORT; locally it defaults to 8000.
CMD uvicorn marketplace.server:app --host 0.0.0.0 --port $PORT
