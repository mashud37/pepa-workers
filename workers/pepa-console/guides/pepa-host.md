# pepa-host

Puts a language model server of your own on Google Cloud or Microsoft Azure, in your own account,
so the workers can write with an open model instead of a hosted service. A server costs nothing
while idle and is billed by the second while it runs.

## How it works

pepa-host builds the server's image in your account with the model inside it, starts it with a
key it makes up, and records its address and key in pepa-host's folder. The server stops when no
request arrives and starts again with the next, so the first request after a pause waits for it.

| Server | Model | Google Cloud | Azure |
|---|---|---|---|
| small | Qwen2.5 3B, on CPU | 8 vCPU, 8 GiB | 4 vCPU, 8 GiB |
| large | Qwen3 32B, on a GPU | NVIDIA L4 | NVIDIA A100 |

On Google Cloud only your own Google account can call the server, so the workers sign in through
the `gcloud` command. On Azure the server's key protects it.

## Use it

1. Install the host's command and sign in: the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install)
   with `gcloud auth login`, or the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli)
   with `az login`. **install** shows which hosts are ready.
2. Run **deploy** and choose the host, the server, and the project or subscription that pays for it.
3. On **Models**, choose **Your own cloud** for a worker and pick the server with **Choose**. Its
   key goes to the **Keys** page by itself.
4. **remove** deletes a server.

## Cost

| Server | Google Cloud, per hour running | Azure, per hour running |
|---|---|---|
| small | $0.76 | $0.43 |
| large | $1.42 | $3.77 |

List prices for europe-west1 and Sweden Central. The image stays in a registry in your account:
Google bills its storage by the gigabyte each month, and Azure's registry costs $0.17 a day. Removing
the last Azure server offers to delete that registry too. Estimates only; check current pricing.

## Other hosts

pepa-host deploys to Google Cloud and Azure only. Both images, in pepa-host's `images` folder, run on
any host that runs a container: build one, set its `API_KEY` variable to a long random key, and serve
port 8080 over HTTPS. On AWS, an EC2 instance does this, with a GPU for the large server. Enter its
address followed by `/v1` on **Models** and the key on **Keys** as `PEPA_LLM_API_KEY`.
