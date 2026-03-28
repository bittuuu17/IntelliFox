#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Intellifox AI — Google Cloud Run Deploy Script
#  Run this from your project folder (where main.py lives)
#  Prerequisites: gcloud CLI installed + authenticated
# ═══════════════════════════════════════════════════════════════

set -e

# ── CONFIGURE THESE TWO VALUES ────────────────────────────────
PROJECT_ID="your-gcp-project-id"       # ← CHANGE THIS
GEMINI_API_KEY="your-gemini-api-key"   # ← CHANGE THIS (from aistudio.google.com)
# ─────────────────────────────────────────────────────────────

SERVICE_NAME="intellifox-api"
REGION="us-central1"
IMAGE="gcr.io/$PROJECT_ID/$SERVICE_NAME"

echo ""
echo "🦊 Deploying Intellifox AI to Google Cloud Run..."
echo "   Project : $PROJECT_ID"
echo "   Service : $SERVICE_NAME"
echo "   Region  : $REGION"
echo ""

# Step 1: Enable required APIs
echo "⚙️  Enabling Cloud Run & Cloud Build APIs..."
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  --project "$PROJECT_ID" --quiet

# Step 2: Build and push image via Cloud Build
echo "🔨 Building container image..."
gcloud builds submit \
  --tag "$IMAGE" \
  --project "$PROJECT_ID"

# Step 3: Deploy to Cloud Run
echo "🚀 Deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --set-env-vars "GEMINI_API_KEY=$GEMINI_API_KEY" \
  --memory 1Gi \
  --cpu 1 \
  --concurrency 20 \
  --max-instances 10 \
  --timeout 120 \
  --project "$PROJECT_ID"

# Step 4: Print URL
echo ""
echo "✅ Deployed! Your app is live at:"
gcloud run services describe "$SERVICE_NAME" \
  --platform managed \
  --region "$REGION" \
  --format 'value(status.url)' \
  --project "$PROJECT_ID"
echo ""
echo "🔗 Open the URL above in your browser to see Intellifox AI!"
