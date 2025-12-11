#!/bin/bash
set -e

echo "🔄 Updating LiteLLM on Cloud VM"
echo ""

# Rebuild and push image
echo "1️⃣ Building and pushing Docker image..."
gcloud builds submit --config=cloudbuild.yaml --project=gen-lang-client-0335698828 .

# Update VM
echo ""
echo "2️⃣ Updating VM (PostgreSQL data will be preserved)..."
gcloud compute ssh litellm-proxy-vm --zone=us-east5-a --command='
  cd /opt/litellm
  sudo docker compose pull litellm-proxy
  sudo docker compose up -d litellm-proxy
  echo "Waiting for service to be healthy..."
  sleep 30
  sudo docker compose ps
'

echo ""
echo "✅ Update complete!"
echo ""
echo "📊 Check status: gcloud compute ssh litellm-proxy-vm --zone=us-east5-a -- 'cd /opt/litellm && sudo docker compose ps'"
echo "📝 View logs:    gcloud compute ssh litellm-proxy-vm --zone=us-east5-a -- 'cd /opt/litellm && sudo docker compose logs -f litellm-proxy'"
echo ""
