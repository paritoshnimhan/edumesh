FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY gateway.py service.py lexicons.py lambda_transcribe.py transcription_client.py index.html ./

EXPOSE 8000

# Kubernetes and Docker Compose override this command for subject services.
CMD ["python", "-m", "uvicorn", "gateway:app", "--host", "0.0.0.0", "--port", "8000"]
