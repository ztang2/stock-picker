FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and pre-built frontend
COPY src/ src/
COPY static/ static/
COPY config.yaml .

# Data directory — mount a volume here at runtime
RUN mkdir -p data
VOLUME ["/app/data"]

EXPOSE 8000

CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
