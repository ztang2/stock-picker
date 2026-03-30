FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ src/
COPY static/ static/
COPY config.yaml .
COPY data/ data/

# Expose port
EXPOSE 8000

# Run the API server
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
