FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY worker/requirements.txt worker/requirements.txt

RUN python -m pip install --no-cache-dir \
    -r worker/requirements.txt

COPY worker/ worker/

CMD ["python", "-m", "worker.daemon", "--interval", "5"]
