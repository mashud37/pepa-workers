# deploy.ps1: build + deploy the pepa-sum summariser service to Cloud Run (Windows).
# Usage: set $env:PROJECT (or `gcloud config set project ...`), then: .\deploy.ps1
#
# Native PowerShell mirror of deploy.sh, keep the two in sync. gcloud_app.yaml
# records the same deployment config declaratively.

$ErrorActionPreference = "Continue"

# PROJECT is normally passed in by `python manage.py deploy` (which prompts).
# When run directly, prompt rather than silently using the active gcloud config.
$PROJECT = $env:PROJECT
if (-not $PROJECT) {
  $current = (gcloud config get-value project 2>$null)
  $PROJECT = Read-Host "GCP project to deploy to [$current]"
  if (-not $PROJECT) { $PROJECT = $current }
}
$REGION = "europe-west1"
$PREFIX = "pepa"
$APP = "pepa-sum"
$IMAGE = "$REGION-docker.pkg.dev/$PROJECT/$PREFIX/app:latest"
$SA = "$PREFIX-sa@$PROJECT.iam.gserviceaccount.com"

if (-not $PROJECT) { Write-Error "No GCP project set."; exit 1 }
if (-not (Test-Path env.yaml)) { Write-Error "env.yaml missing - run: python manage.py install"; exit 1 }

# --- enable APIs ---
gcloud services enable run.googleapis.com storage.googleapis.com `
  artifactregistry.googleapis.com cloudbuild.googleapis.com --project=$PROJECT

# --- Artifact Registry repo (ignore if it already exists) ---
gcloud artifacts repositories create $PREFIX --repository-format=docker `
  --location=$REGION --project=$PROJECT

# --- service account (ignore if it already exists) ---
gcloud iam service-accounts create "$PREFIX-sa" `
  --display-name="pepa-sum - summariser service" --project=$PROJECT

# --- build image (model is baked in; this build is large) ---
# A first build right after the Cloud Build API was just enabled can hit a
# transient PERMISSION_DENIED while the API's permissions propagate. Retry once.
gcloud builds submit --tag $IMAGE --project=$PROJECT .
if ($LASTEXITCODE -ne 0) {
  Write-Host "Build failed; waiting 90s for Cloud Build API permissions to propagate, then retrying once..."
  Start-Sleep -Seconds 90
  gcloud builds submit --tag $IMAGE --project=$PROJECT .
}
if ($LASTEXITCODE -ne 0) { Write-Error "Image build failed."; exit 1 }

# --- deploy service ---
gcloud run deploy $PREFIX --image=$IMAGE --region=$REGION --project=$PROJECT `
  --service-account=$SA --labels="app=$APP" --env-vars-file=env.yaml `
  --allow-unauthenticated --memory=8Gi --cpu=8 `
  --max-instances=1 --concurrency=1 --min-instances=0 --timeout=900
if ($LASTEXITCODE -ne 0) { Write-Error "Deploy failed."; exit 1 }

# --- write BASE_URL back into env.yaml (two-pass) ---
$URL = (gcloud run services describe $PREFIX --region=$REGION --project=$PROJECT `
  --format="value(status.url)")
python -c "import yaml,sys,pathlib;p=pathlib.Path('env.yaml');d=yaml.safe_load(p.read_text()) or {};d['BASE_URL']=sys.argv[1];p.write_text(yaml.safe_dump(d,sort_keys=False));print('BASE_URL written: '+sys.argv[1])" $URL

Write-Host ""
Write-Host "Deployed. Summarise locally with:  python manage.py summarize"
