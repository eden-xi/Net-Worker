# Net-Worker container: the existing app + deploy/server.py wrapper.
FROM python:3.13-slim

# Don't write .pyc files, print logs right away, keep data in /data.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    PORT=8000

WORKDIR /app

# Install libraries first so Docker can cache this step.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the code (.dockerignore keeps the real database and resumes out).
COPY . .

# Run as a normal user, not root.
RUN useradd --create-home appuser \
    && mkdir -p /data \
    && chown -R appuser /app /data
USER appuser

EXPOSE 8000

# Render sets $PORT; locally it defaults to 8000.
CMD uvicorn deploy.server:app --host 0.0.0.0 --port $PORT
