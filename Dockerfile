FROM mcr.microsoft.com/playwright/python:v1.59.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["/bin/sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT:-8080} --timeout 600 --workers 1 --worker-class gthread --threads 4"]
