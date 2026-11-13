# Net-Worker container: the existing app + deploy/server.py wrapper.
# Build from the REPO ROOT:  docker build -f deploy/Dockerfile .
FROM python:3.13-slim

# Don't write .pyc files, print logs right away, keep data in /data.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    PORT=8000

WORKDIR /app

# Install libraries first so Docker can cache this step.
COPY deploy/requirements.txt deploy/requirements.txt
RUN pip install --no-cache-dir -r deploy/requirements.txt

# Copy ONLY the code, file by file. The real database (backend/database/*.db)
# and resumes (uploads/) are never copied, so they can't end up in the image.
COPY backend/api/*.py backend/api/
COPY backend/core/*.py backend/core/
COPY frontend/ frontend/
COPY deploy/*.py deploy/*.csv deploy/

# Run as a normal user, not root.
RUN useradd --create-home appuser \
    && mkdir -p /data \
    && chown -R appuser /app /data
USER appuser

EXPOSE 8000

# Render sets $PORT; locally it defaults to 8000.
CMD uvicorn deploy.server:app --host 0.0.0.0 --port $PORT
