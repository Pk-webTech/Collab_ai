FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Cloud Run injects the $PORT environment variable automatically (usually 8080)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]