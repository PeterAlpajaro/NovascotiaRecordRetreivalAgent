FROM mcr.microsoft.com/playwright/python:v1.53.0-noble

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN mkdir -p /app/downloads /app/archives /app/state

CMD ["python", "-m", "app.worker"]
