#!/bin/bash
set -e

# Configuration
PROJECT_ID="gen-lang-client-0335698828"
ZONE="us-east5-a"
INSTANCE_NAME="litellm-proxy-vm"
MACHINE_TYPE="e2-medium"  # 2 vCPU, 4GB RAM (~$25/month)

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🚀 LiteLLM GCE VM Deployment${NC}"
echo ""

# Check .env exists and has required vars
if [ ! -f .env ]; then
  echo -e "${RED}Error: .env file not found${NC}"
  exit 1
fi

if ! grep -q "LITELLM_MASTER_KEY" .env; then
  echo -e "${RED}Error: LITELLM_MASTER_KEY not set in .env${NC}"
  exit 1
fi

MASTER_KEY=$(grep "LITELLM_MASTER_KEY" .env | cut -d'=' -f2)
POSTGRES_PASSWORD=$(grep "POSTGRES_PASSWORD" .env | cut -d'=' -f2 || echo "litellm_db_$(openssl rand -hex 8)")

echo "Project: $PROJECT_ID"
echo "Zone: $ZONE"
echo "Instance: $INSTANCE_NAME"
echo ""

# Set project
gcloud config set project $PROJECT_ID --quiet

# Check if VM exists
VM_EXISTS=false
if gcloud compute instances describe $INSTANCE_NAME --zone=$ZONE &>/dev/null; then
  VM_EXISTS=true
  echo -e "${YELLOW}VM '$INSTANCE_NAME' already exists.${NC}"
  
  EXTERNAL_IP=$(gcloud compute instances describe $INSTANCE_NAME --zone=$ZONE --format='get(networkInterfaces[0].accessConfigs[0].natIP)')
  
  echo ""
  echo "1) Update config and restart services"
  echo "2) Delete VM and recreate"
  echo "3) Just show connection info"
  echo ""
  read -p "Choose option (1/2/3): " OPTION
  
  case $OPTION in
    1)
      echo "Updating VM..."
      ;;
    2)
      echo "Deleting VM..."
      gcloud compute instances delete $INSTANCE_NAME --zone=$ZONE --quiet
      VM_EXISTS=false
      ;;
    3)
      echo ""
      echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
      echo -e "${GREEN}Connection Info${NC}"
      echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
      echo ""
      echo "API URL:  http://$EXTERNAL_IP:45678/v1"
      echo "UI URL:   http://$EXTERNAL_IP:45678/ui"
      echo "API Key:  $MASTER_KEY"
      echo ""
      echo "SSH:      gcloud compute ssh $INSTANCE_NAME --zone=$ZONE"
      echo "Logs:     gcloud compute ssh $INSTANCE_NAME --zone=$ZONE -- 'cd /opt/litellm && sudo docker-compose logs -f'"
      echo ""
      exit 0
      ;;
    *)
      echo "Invalid option"
      exit 1
      ;;
  esac
fi

if [ "$VM_EXISTS" = false ]; then
  echo "Creating VM..."
  
  # Create VM with Debian (easier than Container-Optimized OS)
  gcloud compute instances create $INSTANCE_NAME \
    --zone=$ZONE \
    --machine-type=$MACHINE_TYPE \
    --image-family=debian-12 \
    --image-project=debian-cloud \
    --boot-disk-size=30GB \
    --tags=http-server,https-server \
    --scopes=cloud-platform
  
  echo "Waiting for VM to be ready..."
  sleep 30
  
  EXTERNAL_IP=$(gcloud compute instances describe $INSTANCE_NAME --zone=$ZONE --format='get(networkInterfaces[0].accessConfigs[0].natIP)')
  
  # Create firewall rule if needed
  gcloud compute firewall-rules describe allow-litellm-proxy &>/dev/null 2>&1 || \
  gcloud compute firewall-rules create allow-litellm-proxy \
    --allow tcp:45678 \
    --target-tags=http-server \
    --description="Allow LiteLLM proxy traffic"
  
  # Install Docker on VM
  echo "Installing Docker on VM..."
  gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --command='
    sudo apt-get update
    sudo apt-get install -y apt-transport-https ca-certificates curl gnupg
    curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian bookworm stable" | sudo tee /etc/apt/sources.list.d/docker.list
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    sudo usermod -aG docker $USER
    sudo mkdir -p /opt/litellm
    sudo chown $USER:$USER /opt/litellm
  '
fi

EXTERNAL_IP=$(gcloud compute instances describe $INSTANCE_NAME --zone=$ZONE --format='get(networkInterfaces[0].accessConfigs[0].natIP)')

echo "Configuring Docker for Artifact Registry..."
gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --command='
  gcloud auth configure-docker us-east5-docker.pkg.dev --quiet
'

# Create remote docker-compose.yml
echo "Creating docker-compose configuration..."
gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --command="cat > /opt/litellm/docker-compose.yml << 'EOF'
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    container_name: litellm-postgres
    environment:
      - POSTGRES_DB=litellm
      - POSTGRES_USER=litellm
      - POSTGRES_PASSWORD=\${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: [\"CMD-SHELL\", \"pg_isready -U litellm\"]
      interval: 5s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  litellm-proxy:
    image: us-east5-docker.pkg.dev/gen-lang-client-0335698828/litellm-repo/litellm-proxy:latest
    container_name: litellm-proxy
    ports:
      - \"45678:45678\"
    volumes:
      - ./config.yaml:/app/config.yaml:ro
    environment:
      - LITELLM_MASTER_KEY=\${LITELLM_MASTER_KEY}
      - DATABASE_URL=postgresql://litellm:\${POSTGRES_PASSWORD}@postgres:5432/litellm
    command: [\"--config\", \"/app/config.yaml\", \"--port\", \"45678\"]
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: [\"CMD-SHELL\", \"python3 -c \\\"import urllib.request; urllib.request.urlopen('http://127.0.0.1:45678/health/readiness')\\\" || exit 1\"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 90s
    restart: unless-stopped

volumes:
  postgres_data:
EOF"

# Create remote config.yaml
echo "Creating LiteLLM configuration..."
gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --command="cat > /opt/litellm/config.yaml << 'EOF'
model_list:
  - model_name: claude-sonnet-4.5
    litellm_params:
      model: vertex_ai/claude-sonnet-4-5@20250929
      vertex_project: gen-lang-client-0335698828
      vertex_location: us-east5
      drop_params: true

  - model_name: claude-4.5-sonnet
    litellm_params:
      model: vertex_ai/claude-sonnet-4-5@20250929
      vertex_project: gen-lang-client-0335698828
      vertex_location: us-east5
      drop_params: true

  - model_name: claude-4.5-sonnet-thinking
    litellm_params:
      model: vertex_ai/claude-sonnet-4-5@20250929
      vertex_project: gen-lang-client-0335698828
      vertex_location: us-east5
      drop_params: true

  - model_name: claude-opus-4.5
    litellm_params:
      model: vertex_ai/claude-opus-4-5@20251101
      vertex_project: gen-lang-client-0335698828
      vertex_location: us-east5
      drop_params: true

  - model_name: claude-4.5-opus
    litellm_params:
      model: vertex_ai/claude-opus-4-5@20251101
      vertex_project: gen-lang-client-0335698828
      vertex_location: us-east5
      drop_params: true

  - model_name: claude-4.5-opus-thinking
    litellm_params:
      model: vertex_ai/claude-opus-4-5@20251101
      vertex_project: gen-lang-client-0335698828
      vertex_location: us-east5
      drop_params: true

  - model_name: \"claude-*\"
    litellm_params:
      model: vertex_ai/claude-sonnet-4-5@20250929
      vertex_project: gen-lang-client-0335698828
      vertex_location: us-east5
      drop_params: true

litellm_settings:
  drop_params: true
  num_retries: 3
  request_timeout: 600
  telemetry: false
  set_verbose: true

general_settings:
  database_url: os.environ/DATABASE_URL
  master_key: os.environ/LITELLM_MASTER_KEY
  ui_username: admin
  ui_password: os.environ/LITELLM_MASTER_KEY
EOF"

# Create remote .env
echo "Creating environment file..."
gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --command="cat > /opt/litellm/.env << EOF
LITELLM_MASTER_KEY=$MASTER_KEY
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
EOF"

# Pull image and start services
echo "Pulling Docker image and starting services..."
gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --command='
  cd /opt/litellm
  sudo docker compose pull
  sudo docker compose up -d
  echo "Waiting for services to start..."
  sleep 30
  sudo docker compose ps
'

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Deployment Complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "🌐 API URL:     http://$EXTERNAL_IP:45678/v1"
echo "🎨 UI URL:      http://$EXTERNAL_IP:45678/ui"
echo "🔑 API Key:     $MASTER_KEY"
echo "👤 UI Login:    admin / $MASTER_KEY"
echo ""
echo "📋 For Cursor:"
echo "   Base URL: http://$EXTERNAL_IP:45678/v1"
echo "   API Key:  $MASTER_KEY"
echo ""
echo "💡 Useful Commands:"
echo "   SSH:     gcloud compute ssh $INSTANCE_NAME --zone=$ZONE"
echo "   Logs:    gcloud compute ssh $INSTANCE_NAME --zone=$ZONE -- 'cd /opt/litellm && sudo docker compose logs -f'"
echo "   Restart: gcloud compute ssh $INSTANCE_NAME --zone=$ZONE -- 'cd /opt/litellm && sudo docker compose restart'"
echo "   Stop:    gcloud compute ssh $INSTANCE_NAME --zone=$ZONE -- 'cd /opt/litellm && sudo docker compose down'"
echo ""
echo "💰 Estimated Cost: ~\$25/month (e2-medium + 30GB disk)"
echo ""
echo "⚠️  Note: This is HTTP only. For HTTPS, set up a domain + nginx + certbot."
echo ""
