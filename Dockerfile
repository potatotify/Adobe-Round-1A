FROM python:3.9-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy your main application
COPY main.py /app/

# Create input/output directories (they'll be mounted at runtime)
RUN mkdir -p /app/input /app/output

# Run your application
CMD ["python", "main.py"]
