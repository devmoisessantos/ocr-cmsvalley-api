# Imagem única com a API e o painel. Usada no Hugging Face Spaces
# (SDK: docker, porta 7860) e em qualquer outro host de container.
FROM python:3.11-slim

# O Hugging Face executa o container com o usuário 1000.
RUN useradd -m -u 1000 appuser
USER appuser
ENV HOME=/home/appuser \
    PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PORT=7860

WORKDIR /app

COPY --chown=appuser:appuser requirements.txt ./
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=appuser:appuser . .

WORKDIR /app/api
EXPOSE 7860
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-7860}"]
