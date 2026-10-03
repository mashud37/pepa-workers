# Models

Summaries, reviews, outlines and drafts are written by a language model. Each worker uses
Anthropic's Claude unless the **Models** page names another. Any service that accepts OpenAI's chat
format works the same way (experimental): DeepSeek, Kimi, Qwen and GLM, or a model running on this
computer in Ollama, LM Studio or vLLM.

## Choosing a model

1. On **Models**, choose where a worker's model runs: **Claude**, **Another service**, **This
   computer** or **Your own cloud**.
2. For Claude, pick the model from the list.
3. Otherwise, pick the server's address with **Choose** or type it, then **Show models** lists the
   models that server offers.
4. For a hosted service, add its key on **Keys** as `PEPA_LLM_API_KEY`. A server on this computer
   needs no key.

pepa-review and pepa-plan use two models: one for the many short steps, such as labelling every
paragraph, and one for the writing.

| Provider | Address |
|---|---|
| DeepSeek | `https://api.deepseek.com/v1` |
| Kimi | `https://api.moonshot.ai/v1`, in mainland China `https://api.moonshot.cn/v1` |
| Qwen | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`, in mainland China `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| GLM | `https://open.bigmodel.cn/api/paas/v4` |
| Hugging Face | `https://router.huggingface.co/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` |
| Ollama | `http://localhost:11434/v1` |
| LM Studio | `http://localhost:1234/v1` |
| vLLM | `http://localhost:8000/v1` |

Batch mode, which halves the price of a large run, uses Anthropic's batch service and runs only
with Claude.

## A model on this computer

With [Ollama](https://ollama.com) installed, `ollama pull qwen3:8b` fetches a model. Its address is
`http://localhost:11434/v1` and its name `qwen3:8b`, and nothing leaves the computer.

pepa-sum sends each paper whole when it fits the model's context window, 32,768 tokens unless
`CONTEXT_TOKENS` in pepa-sum's `env.yaml` says otherwise. Ollama drops whatever goes past its own
context length, so start it with `OLLAMA_CONTEXT_LENGTH` set to the same number.

## A model in your own cloud

pepa-sum's **deploy** puts Qwen2.5 3B on Google Cloud Run in your own project and points pepa-sum at
it. Only your own Google account can call it: each worker signs in through the `gcloud` command, so
it must be installed and signed in.

pepa-draft's `cloud/Dockerfile.vllm` runs a larger model, Qwen3 32B, on a Cloud Run GPU. Deploy it
with an `API_KEY` variable and `--no-allow-unauthenticated`, then enter its address followed by
`/v1` and that key as for any other server.

## Embeddings

pepa-review's index and pepa-draft's style matching compare texts by their embeddings, a list of
numbers for each text. Both use Gemini unless the Models page names another provider. DeepSeek and
Kimi offer no embeddings; Qwen does (`text-embedding-v4`), and Ollama runs one on this computer
(`ollama pull bge-m3`). A hosted provider's key goes on **Keys** as `PEPA_EMBED_API_KEY`.

The index records the model that built it and refuses any other. After a change, rebuild it: run
pepa-review's index command with **Rebuild from scratch** ticked.
