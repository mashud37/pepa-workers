# pepa-host

Puts a language model server of your own on Google Cloud or Microsoft Azure, in your own account,
so the pepa workers can write with an open model instead of a hosted service. The server speaks
OpenAI's chat format, costs nothing while idle, and is billed by the second while it runs.

## Layout

```
manage.py      entrypoint, no arguments opens the menu
settings.py    the two servers, their models, and their size on each host
cli/           the commands
hosts/         Google Cloud (Cloud Run) and Azure (Container Apps)
images/        small: llama.cpp on CPU; large: vLLM on a GPU, behind a proxy that waits for the model
data/          servers.json, each deployed server's address and key (gitignored)
```

## Setup

Install the host's command and sign in: the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install)
with `gcloud auth login`, or the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli)
with `az login`.

```
python manage.py install
```

## Commands

| Action | Command |
|---|---|
| Put a server on a host | `python manage.py deploy --host gcloud --server small` |
| List the deployed servers | `python manage.py list` |
| Delete a server | `python manage.py remove small-gcloud` |
| Check which hosts are ready | `python manage.py install` |

No arguments opens the menu. `deploy` asks for the project or subscription, then for a yes before
anything is built.

## Servers

| Server | Model | Google Cloud | Azure |
|---|---|---|---|
| small | Qwen2.5 3B, Q4_K_M, 32k context | 8 vCPU, 8 GiB | 4 vCPU, 8 GiB |
| large | Qwen3 32B AWQ | NVIDIA L4, 8k context | NVIDIA A100, 32k context |

On Google Cloud the server refuses anyone but your own Google account, and the workers sign in
through `gcloud`; on Azure the server's key protects it. The console's Models page offers every
server in `data/servers.json` under **Your own cloud** and gives the chosen worker its key.

The images take the model as build arguments: `MODEL_GGUF_URL` and `MODEL_GGUF_SHA256` for small,
`MODEL` for large. To serve another model, change their defaults and the model name in `settings.py`.

## Cost

| Server | Google Cloud, per hour running | Azure, per hour running |
|---|---|---|
| small | $0.76 | $0.43 |
| large | $1.42 | $3.77 |

List prices for europe-west1 and Sweden Central (`PEPAHOST_GCLOUD_REGION`, `PEPAHOST_AZURE_REGION`).
The image stays in a registry in your account: Google bills its storage by the gigabyte each month,
and Azure's registry costs $0.17 a day until you delete it, which removing the last server offers. Estimates only;
check current pricing.
