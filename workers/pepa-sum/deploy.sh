#!/usr/bin/env bash
# deploy.sh — build + deploy the pepa-sum summariser service to Cloud Run.
# Usage: set PROJECT below (or `gcloud config set project ...`), then: bash deploy.sh
#
# NOTE: gcloud_app.yaml records the same deployment config declaratively;
#       keep the two in sync.

set -euo pipefail

# PROJECT is normally passed in by `python manage.py deploy` (which prompts).
# When run directly, prompt rather than silently using the active gcloud config.
if [ -z "${PROJECT:-}" ]; then
  current="$(gcloud config get-value project 2>/dev/null)"
  read -r -p "GCP project to deploy to [${current}]: " PROJECT
  PROJECT="${PROJECT:-$current}"
fi
REGION=europe-west1
PREFIX=pepa
APP=pepa-sum
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${PREFIX}/app:latest"
SA="${PREFIX}-sa@${PROJECT}.iam.gserviceaccount.com"

[ -n "${PROJECT}" ] || { echo "No GCP project set."; exit 1; }
[ -f env.yaml ] || { echo "env.yaml missing — run: python manage.py install"; exit 1; }

# ── enable APIs ───────────────────────────────────────────────────────────────
gcloud services enable \
  run.googleapis.com \
  storage.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  --project="${PROJECT}"

# ── Artifact Registry repo ────────────────────────────────────────────────────
gcloud artifacts repositories create "${PREFIX}" \
  --repository-format=docker \
  --location="${REGION}" \
  --project="${PROJECT}" 2>/dev/null || true

# ── service account ───────────────────────────────────────────────────────────
gcloud iam service-accounts create "${PREFIX}-sa" \
  --display-name="pepa-sum — summariser service" \
  --project="${PROJECT}" 2>/dev/null || true

# ── build image (model is baked in; this build is large) ──────────────────────
# A first build right after the Cloud Build API was just enabled can hit a
# transient PERMISSION_DENIED while the API's permissions propagate. Retry once.
gcloud builds submit --tag "${IMAGE}" --project="${PROJECT}" . || {
  echo "Build failed; waiting 90s for Cloud Build API permissions to propagate, then retrying once..."
  sleep 90
  gcloud builds submit --tag "${IMAGE}" --project="${PROJECT}" .
}

# ── deploy service ────────────────────────────────────────────────────────────
gcloud run deploy "${PREFIX}" \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --project="${PROJECT}" \
  --service-account="${SA}" \
  --labels="app=${APP}" \
  --env-vars-file=env.yaml \
  --allow-unauthenticated \
  --memory=8Gi --cpu=8 \
  --max-instances=1 --concurrency=1 \
  --min-instances=0 \
  --timeout=900

# ── write BASE_URL back into env.yaml (two-pass) ──────────────────────────────
URL="$(gcloud run services describe "${PREFIX}" --region="${REGION}" \
  --project="${PROJECT}" --format='value(status.url)')"
python - "$URL" <<'PY'
import sys, yaml, pathlib
url = sys.argv[1]
p = pathlib.Path("env.yaml")
data = yaml.safe_load(p.read_text()) or {}
data["BASE_URL"] = url
p.write_text(yaml.safe_dump(data, sort_keys=False))
print(f"BASE_URL written: {url}")
PY

echo ""
echo "Deployed. Summarise locally with:  python manage.py summarize"
