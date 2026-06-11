"""Run the instruction-tuned GGUF model on CPU via llama-cpp-python.

The model is loaded once, lazily, on the first request (so a cold instance
starts fast and only pays the load when actually used)."""
import os
from functools import lru_cache

MODEL_PATH = os.environ.get("MODEL_PATH", "/models/model.gguf")
_N_CTX = int(os.environ.get("N_CTX", "16384"))
_MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "1400"))


@lru_cache(maxsize=1)
def _llm():
    from llama_cpp import Llama
    return Llama(model_path=MODEL_PATH, n_ctx=_N_CTX, n_threads=os.cpu_count(), verbose=False)


def generate(system, prompt):
    out = _llm().create_chat_completion(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        max_tokens=_MAX_TOKENS,
        temperature=0.2,
    )
    return out["choices"][0]["message"]["content"].strip()
