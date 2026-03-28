#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
#  Intellifox AI — ONE-SHOT GCP Deploy Script (Vertex AI, no API key needed)
#  Run this from your project folder:
#    chmod +x deploy_gcp.sh
#    ./deploy_gcp.sh
# ═══════════════════════════════════════════════════════════════════════════════
set -e

# ════════════════════════════════════════════════════════
# ▼▼▼  CHANGE ONLY THESE TWO LINES  ▼▼▼
PROJECT_ID="intellifox-ai"   # e.g. intellifox-ai-123456
REGION="us-central1"
# ▲▲▲  THAT'S IT  ▲▲▲
# ════════════════════════════════════════════════════════

SERVICE_NAME="intellifox-api"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  🦊 Intellifox AI — GCP Vertex AI Deploy             ║"
echo "╚══════════════════════════════════════════════════════╝"
echo "  Project : $PROJECT_ID"
echo "  Region  : $REGION"
echo "  Service : $SERVICE_NAME"
echo ""

# ── STEP 1: Set GCP project ──────────────────────────────────────────────────
echo "⚙️  [1/6] Setting GCP project..."
gcloud config set project "$PROJECT_ID"

# ── STEP 2: Enable all required APIs ─────────────────────────────────────────
echo "⚙️  [2/6] Enabling APIs (takes ~60 seconds)..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  aiplatform.googleapis.com \
  containerregistry.googleapis.com \
  --project "$PROJECT_ID" --quiet

# ── STEP 3: Grant Cloud Run Service Account access to Vertex AI ───────────────
echo "🔑 [3/6] Granting Vertex AI permissions to Cloud Run..."
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA}" \
  --role="roles/aiplatform.user" \
  --quiet

echo "   ✅ Service account $SA has Vertex AI access"

# ── STEP 4: Build container image via Cloud Build ─────────────────────────────
echo "🔨 [4/6] Building container image on GCP (3-5 min)..."
gcloud builds submit \
  --tag "$IMAGE" \
  --project "$PROJECT_ID"

echo "   ✅ Image built: $IMAGE"

# ── STEP 5: Deploy to Cloud Run ───────────────────────────────────────────────
echo "🚀 [5/6] Deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},RUN_ENV=production,UVICORN_HOST=0.0.0.0,UVICORN_RELOAD=0" \
  --memory 2Gi \
  --cpu 1 \
  --concurrency 10 \
  --max-instances 5 \
  --timeout 300 \
  --service-account "${SA}" \
  --project "$PROJECT_ID"

# ── STEP 6: Print URL and test ────────────────────────────────────────────────
echo ""
echo "✅ [6/6] Deployed successfully!"
URL=$(gcloud run services describe "$SERVICE_NAME" \
  --platform managed \
  --region "$REGION" \
  --format "value(status.url)" \
  --project "$PROJECT_ID")

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  🎉 INTELLIFOX AI IS LIVE!                           ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  🌐 App URL  : $URL"
echo "  ❤️  Health   : $URL/health"
echo ""
echo "  Test commands:"
echo "  curl $URL/health"
echo ""
echo "  curl -X POST $URL/api/chat \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"message\":\"What is the Core Banking System?\",\"history\":[]}'"
echo ""
echo "  Open in browser: $URL"
echo ""
