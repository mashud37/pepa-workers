# pepa-sum self-hosted model: llama.cpp's OpenAI-compatible server on CPU, the model baked in.
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ cmake curl && rm -rf /var/lib/apt/lists/*

COPY requirements-serve.txt .
RUN pip install --no-cache-dir -r requirements-serve.txt

ARG MODEL_GGUF_URL=https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf
ARG MODEL_ALIAS=qwen2.5-3b-instruct
RUN mkdir -p /models && curl -fSL "$MODEL_GGUF_URL" -o /models/model.gguf

ENV MODEL=/models/model.gguf
ENV MODEL_ALIAS=${MODEL_ALIAS}
ENV HOST=0.0.0.0
ENV N_CTX=16384
ENV N_THREADS=8

CMD ["python", "-m", "llama_cpp.server"]
