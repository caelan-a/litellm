# Deployment Guide

## Overview

Your LiteLLM proxy with custom Vertex AI Claude fixes runs on:
- **Development:** Docker locally with ngrok
- **Production:** GCE VM with persistent PostgreSQL

Both use your custom Docker image with all tool-calling fixes baked in.

---

## 🚀 Initial Deployment (One-Time Setup)

### Prerequisites

```bash
# Ensure you're authenticated
gcloud auth login
gcloud config set project gen-lang-client-0335698828

# Ensure .env file has required variables
cat .env
# Should contain:
# LITELLM_MASTER_KEY=your_key_here
# POSTGRES_PASSWORD=your_db_password_here
# NGROK_AUTHTOKEN=your_ngrok_token_here
```

### Deploy to Cloud

```bash
make init-cloud
```

This will:
1. Create a GCE VM (e2-medium, us-east5-a)
2. Install Docker
3. Build and push your custom image
4. Start PostgreSQL + LiteLLM proxy
5. Configure firewall rules

**Output:** Public IP address and connection details

**Cost:** ~$25/month

---

## 🔄 Updating Code

After making changes to your LiteLLM code:

```bash
make deploy
```

This will:
1. Rebuild your custom Docker image
2. Push to Artifact Registry
3. Pull new image on VM
4. Restart only the proxy container
5. **PostgreSQL data is preserved** ✅

**Downtime:** ~30 seconds

---

## 🛠️ Development Workflow

### Local Development

```bash
# Start local stack (Docker + PostgreSQL + ngrok)
make start

# View logs
make logs-watch

# Restart after code changes (hot reload via volume mount)
make restart

# Stop everything
make stop-all
```

**Note:** Local uses volume mounts for hot reload. No rebuild needed for code changes.

### Testing Changes Locally

1. Edit `litellm/llms/vertex_ai/vertex_ai_partner_models/anthropic/transformation.py`
2. Run `make restart` (or just restart the container - volume mount picks up changes)
3. Test with Cursor pointing to ngrok URL
4. When satisfied, deploy to cloud with `make deploy`

---

## 📊 Monitoring & Management

### Check Status

```bash
# Cloud VM status
gcloud compute ssh litellm-proxy-vm --zone=us-east5-a -- 'cd /opt/litellm && sudo docker compose ps'

# View logs
gcloud compute ssh litellm-proxy-vm --zone=us-east5-a -- 'cd /opt/litellm && sudo docker compose logs -f litellm-proxy'

# Health check
curl http://34.186.232.98:45678/health -H "Authorization: Bearer YOUR_MASTER_KEY"
```

### SSH to VM

```bash
gcloud compute ssh litellm-proxy-vm --zone=us-east5-a
```

### Restart Services

```bash
# Just the proxy (keeps database running)
gcloud compute ssh litellm-proxy-vm --zone=us-east5-a -- 'cd /opt/litellm && sudo docker compose restart litellm-proxy'

# All services
gcloud compute ssh litellm-proxy-vm --zone=us-east5-a -- 'cd /opt/litellm && sudo docker compose restart'
```

---

## 💾 Data Persistence

### PostgreSQL Data Location

**Local:**
- `./postgres_data/` directory
- Persists across restarts

**Cloud VM:**
- Docker named volume: `postgres_data`
- Located at: `/var/lib/docker/volumes/litellm_postgres_data/`
- Survives: Container restarts, image updates, `docker-compose down/up`

### Backup Database

```bash
# Cloud VM
gcloud compute ssh litellm-proxy-vm --zone=us-east5-a -- '
  cd /opt/litellm
  sudo docker compose exec postgres pg_dump -U litellm litellm > backup_$(date +%Y%m%d).sql
'

# Download backup
gcloud compute scp litellm-proxy-vm:/opt/litellm/backup_*.sql ./backups/ --zone=us-east5-a
```

### Restore Database

```bash
# Upload backup
gcloud compute scp ./backups/backup_YYYYMMDD.sql litellm-proxy-vm:/opt/litellm/ --zone=us-east5-a

# Restore
gcloud compute ssh litellm-proxy-vm --zone=us-east5-a -- '
  cd /opt/litellm
  cat backup_YYYYMMDD.sql | sudo docker compose exec -T postgres psql -U litellm litellm
'
```

---

## 🔐 Security

### Environment Variables

**Never commit:**
- `.env` (in `.gitignore`)
- `postgres_data/` (in `.gitignore`)

**Keys are set in:**
- Local: `.env` file
- Cloud VM: `/opt/litellm/.env` (copied during deployment)

### Firewall

Only port `45678` is exposed for the proxy.
PostgreSQL (5432) is internal to Docker network only.

---

## 🐛 Troubleshooting

### VM Won't Start Services

```bash
# Check Docker is running
gcloud compute ssh litellm-proxy-vm --zone=us-east5-a -- 'sudo systemctl status docker'

# Check for image pull errors
gcloud compute ssh litellm-proxy-vm --zone=us-east5-a -- 'cd /opt/litellm && sudo docker compose logs'

# Re-authenticate Docker
gcloud compute ssh litellm-proxy-vm --zone=us-east5-a -- 'sudo gcloud auth configure-docker us-east5-docker.pkg.dev --quiet'
```

### Database Connection Issues

```bash
# Check PostgreSQL is healthy
gcloud compute ssh litellm-proxy-vm --zone=us-east5-a -- 'cd /opt/litellm && sudo docker compose ps postgres'

# Check database logs
gcloud compute ssh litellm-proxy-vm --zone=us-east5-a -- 'cd /opt/litellm && sudo docker compose logs postgres'

# Restart database
gcloud compute ssh litellm-proxy-vm --zone=us-east5-a -- 'cd /opt/litellm && sudo docker compose restart postgres'
```

### Image Build Fails

```bash
# Check build logs
gcloud builds list --limit=5

# View specific build
gcloud builds log BUILD_ID
```

### Can't Pull Custom Image

This happens when VM service account doesn't have permissions:

```bash
# Grant permissions
gcloud artifacts repositories add-iam-policy-binding litellm-repo \
  --location=us-east5 \
  --member="serviceAccount:228973215278-compute@developer.gserviceaccount.com" \
  --role="roles/artifactregistry.reader" \
  --project=gen-lang-client-0335698828

# Re-authenticate on VM
gcloud compute ssh litellm-proxy-vm --zone=us-east5-a -- 'sudo gcloud auth configure-docker us-east5-docker.pkg.dev --quiet'
```

---

## 💰 Cost Management

### Current Setup

- **GCE VM (e2-medium):** ~$25/month
- **Persistent disk (30GB):** ~$2/month
- **Artifact Registry:** Free tier (up to 0.5GB)
- **Egress:** Variable (depends on usage)

**Total:** ~$25-30/month

### To Reduce Costs

1. **Use a smaller VM:**
   ```bash
   # e2-small (2GB RAM, 1 vCPU) - ~$12/month
   # Good for low traffic
   ```

2. **Use a preemptible VM:**
   ```bash
   # Add --preemptible flag to gcloud compute instances create
   # ~70% cheaper but can be terminated
   ```

3. **Stop VM when not in use:**
   ```bash
   gcloud compute instances stop litellm-proxy-vm --zone=us-east5-a
   
   # Start again
   gcloud compute instances start litellm-proxy-vm --zone=us-east5-a
   ```

---

## 🗑️ Cleanup

### Delete VM (Keep Data)

```bash
# Stop VM
gcloud compute instances stop litellm-proxy-vm --zone=us-east5-a

# Delete VM but keep disk
gcloud compute instances delete litellm-proxy-vm --zone=us-east5-a --keep-disks=boot
```

### Delete Everything

```bash
# Delete VM
gcloud compute instances delete litellm-proxy-vm --zone=us-east5-a --quiet

# Delete firewall rule
gcloud compute firewall-rules delete allow-litellm-proxy --quiet

# Delete Cloud SQL (if you ever set one up)
gcloud sql instances delete litellm-db --quiet

# Clean up images
gcloud artifacts docker images list us-east5-docker.pkg.dev/gen-lang-client-0335698828/litellm-repo
gcloud artifacts docker images delete IMAGE_NAME --delete-tags --quiet
```

---

## 📚 Architecture

### Components

```
┌─────────────────────────────────────────┐
│           GCE VM (e2-medium)            │
│  ┌───────────────────────────────────┐  │
│  │  Docker Compose                   │  │
│  │  ┌─────────────┐  ┌──────────┐   │  │
│  │  │ LiteLLM     │  │ Postgres │   │  │
│  │  │ Proxy       │──│ Database │   │  │
│  │  │ :45678      │  │ :5432    │   │  │
│  │  │             │  │          │   │  │
│  │  │ Custom      │  │ Volume:  │   │  │
│  │  │ Image       │  │ postgres │   │  │
│  │  │ (Artifact   │  │ _data    │   │  │
│  │  │  Registry)  │  │          │   │  │
│  │  └─────────────┘  └──────────┘   │  │
│  └───────────────────────────────────┘  │
│                                         │
│  Firewall: Port 45678 open             │
└─────────────────────────────────────────┘
           │
           │ HTTP
           ▼
      [Cursor / Users]
```

### Custom Image Contents

- **Base:** Python 3.11
- **Your fixes:** `litellm/llms/vertex_ai/vertex_ai_partner_models/anthropic/transformation.py`
  - Anthropic format detection
  - Thinking block stripping
  - Tool choice sanitization
- **Config:** `litellm_vertex_claude_config.yaml`
- **Dependencies:** 
  - google-cloud-aiplatform
  - prisma
  - All LiteLLM proxy dependencies

---

## 🎯 Quick Reference

| Task | Command |
|------|---------|
| Initial cloud setup | `make init-cloud` |
| Deploy code updates | `make deploy` |
| Start local dev | `make start` |
| Stop local dev | `make stop-all` |
| View logs (local) | `make logs-watch` |
| View logs (cloud) | `gcloud compute ssh litellm-proxy-vm --zone=us-east5-a -- 'cd /opt/litellm && sudo docker compose logs -f'` |
| SSH to VM | `gcloud compute ssh litellm-proxy-vm --zone=us-east5-a` |
| Restart cloud | `gcloud compute ssh litellm-proxy-vm --zone=us-east5-a -- 'cd /opt/litellm && sudo docker compose restart'` |

---

## 🔗 URLs

**Development (Local):**
- Proxy: `https://mathias-unrelayed-scribbly.ngrok-free.dev/v1`
- UI: `https://mathias-unrelayed-scribbly.ngrok-free.dev/ui`
- ngrok changes on restart

**Production (Cloud VM):**
- Proxy: `http://34.186.232.98:45678/v1`
- UI: `http://34.186.232.98:45678/ui`
- IP is stable (unless you delete/recreate VM)

**For HTTPS on cloud:**
- Set up a domain pointing to the VM IP
- Use nginx + certbot for Let's Encrypt SSL
- Or use Cloudflare Tunnel (free)
