FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ cmake curl && rm -rf /var/lib/apt/lists/*

COPY requirements-serve.txt .
RUN pip install --no-cache-dir -r requirements-serve.txt

# Bake the instruction-tuned model into the image so inference is ready on a
# cold start. Override the URL at build time to swap models.
ARG MODEL_GGUF_URL=https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf
RUN mkdir -p /models && curl -fSL "$MODEL_GGUF_URL" -o /models/model.gguf

COPY serve/ ./serve/

ENV MODEL_PATH=/models/model.gguf
ENV PORT=8080
# One worker (the model is large); no request timeout — CPU generation is slow.
CMD ["sh", "-c", "gunicorn -b 0.0.0.0:${PORT} -w 1 -t 0 serve.app:app"]
