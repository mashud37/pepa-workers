# pepa-sum self-hosted model: llama.cpp's OpenAI-compatible server on CPU, the model baked in.
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ cmake curl && rm -rf /var/lib/apt/lists/*

COPY requirements-serve.txt .
RUN pip install --no-cache-dir -r requirements-serve.txt

ARG MODEL_GGUF_URL=https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/7dabda4d13d513e3e842b20f0d435c732f172cbe/qwen2.5-3b-instruct-q4_k_m.gguf
ARG MODEL_GGUF_SHA256=626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d
ARG MODEL_ALIAS=qwen2.5-3b-instruct
RUN mkdir -p /models && curl -fSL "$MODEL_GGUF_URL" -o /models/model.gguf \
    && echo "$MODEL_GGUF_SHA256  /models/model.gguf" | sha256sum -c -

ENV MODEL=/models/model.gguf
ENV MODEL_ALIAS=${MODEL_ALIAS}
ENV HOST=0.0.0.0
ENV N_CTX=16384
ENV N_THREADS=8

CMD ["python", "-m", "llama_cpp.server"]
