FROM python:3.12-slim as builder

WORKDIR /build

COPY requirements.txt .

RUN pip install --user --no-cache-dir -r requirements.txt


FROM python:3.12-slim as runtime

WORKDIR /app

# Add user-local bin to PATH and set unbuffered output early
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy Python packages from builder (layer caching)
COPY --from=builder /root/.local /root/.local

# Copy only app code (alembic migrations included via volume in compose)
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

# Non-root user for security (optional but recommended)
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Default command - override in docker-compose for migrate/worker
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
