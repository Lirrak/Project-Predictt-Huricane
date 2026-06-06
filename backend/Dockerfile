FROM python:3.10-slim

WORKDIR /workspace

# Install system dependencies (curl for healthchecks, libgomp for XGBoost)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy backend requirements first to leverage Docker layer caching
COPY requirements.txt .

# Install Python package dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source code and models
COPY backend/app ./app
COPY models/ ./models
COPY data/ ./data

EXPOSE 8000

ENV PYTHONPATH=/workspace

# Start FastAPI server using uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
