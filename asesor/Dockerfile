# Imagen base con CUDA 12.4 + cuDNN 9: es lo que necesita CTranslate2
# (el motor de faster-whisper) para correr en GPU. Si algún día quitas la
# GPU, puedes cambiar a python:3.11-slim y poner WHISPER_DEVICE=cpu.
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Madrid

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        ca-certificates \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Primero las dependencias (capa cacheada: no se reinstalan si solo cambias código)
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY prompts/ prompts/

CMD ["python3", "-m", "src.main"]
