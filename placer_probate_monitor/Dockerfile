FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY placer_probate_monitor.py ecourt_client.py pdf_report.py petition_parse.py addon_server.py /app/
COPY www /app/www

EXPOSE 8099

CMD ["python3", "-u", "/app/addon_server.py"]
