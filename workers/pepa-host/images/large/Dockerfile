# pepa-host large server: vLLM's OpenAI-compatible server behind a proxy that holds requests while the model loads.
FROM vllm/vllm-openai:v0.30.0

ARG MODEL=Qwen/Qwen3-32B-AWQ
ENV MODEL=${MODEL}
ENV MAX_MODEL_LEN=8192

WORKDIR /app

RUN pip install --no-cache-dir flask gunicorn

COPY serve_vllm.py /app/serve_vllm.py

ENTRYPOINT ["sh", "-c", "vllm serve ${MODEL} --served-model-name ${MODEL} --api-key ${API_KEY} --max-model-len ${MAX_MODEL_LEN} --port 8001 --tensor-parallel-size 1 & gunicorn -w 1 -t 0 -b 0.0.0.0:8080 serve_vllm:app"]
