# Vertex AI Claude Proxy - Docker Setup

Easy Docker-based setup for using Claude models from Google Vertex AI via LiteLLM proxy + ngrok tunnel.

## Quick Start

### 1. Create `.env` File

```bash
# Copy the example file
cp .env.example .env

# Edit .env and add your ngrok token
# Get token from: https://dashboard.ngrok.com/get-started/your-authtoken
```

Your `.env` file should look like:
```
NGROK_AUTHTOKEN=your_actual_token_here
```

### 2. Setup Google Cloud Credentials

```bash
# Login to Google Cloud (one-time setup)
gcloud auth application-default login
```

### 3. Start Everything

```bash
# Start proxy + ngrok in Docker
make start

# Get your public URL and Cursor config
make url
```

## Easy Commands

```bash
make start         # 🚀 Start proxy + ngrok
make stop-all      # 🛑 Stop everything  
make restart       # 🔄 Restart everything
make url           # 📡 Show ngrok URL & Cursor config
make proxy-status  # 📊 Show service status
make logs          # 📜 Show proxy logs
make logs-follow   # 📜 Follow logs in real-time
```

## Cursor IDE Configuration

After running `make start` and `make url`, you'll get:

```
API Base URL:  https://your-unique-id.ngrok-free.app/v1
API Key:       (any value works)

Available Models:
  • claude-sonnet-4.5
  • claude-4.5-sonnet
  • claude-4.5-sonnet-thinking
  • claude-opus-4.5
  • claude-4.5-opus
  • claude-4.5-opus-thinking
```

## Troubleshooting

### Ngrok Authentication Error

```bash
# Make sure .env file exists and has your token
cat .env | grep NGROK_AUTHTOKEN

# If missing, copy the example and edit:
cp .env.example .env
# Then edit .env with your actual token
```

### Google Cloud Authentication Error

```bash
# Re-authenticate
gcloud auth application-default login

# Check credentials exist
ls ~/.config/gcloud/application_default_credentials.json
```

### Check Logs

```bash
# Proxy logs
make logs

# Ngrok logs  
make logs-ngrok

# Follow logs in real-time
make logs-follow
```

## Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────────┐
│   Cursor    │─────▶│    Ngrok     │─────▶│  LiteLLM Proxy  │
│     IDE     │      │   (public)   │      │    (Docker)     │
└─────────────┘      └──────────────┘      └─────────────────┘
                                                     │
                                                     ▼
                                            ┌─────────────────┐
                                            │  Vertex AI      │
                                            │  Claude Models  │
                                            └─────────────────┘
```

## What's Running?

- **LiteLLM Proxy** (Docker container): Translates OpenAI API calls to Vertex AI format
- **Ngrok** (Docker container): Exposes proxy to the internet with HTTPS
- **Config**: Your Vertex AI project settings in `litellm_vertex_claude_config.yaml`

## Persistence

- Containers auto-restart unless stopped
- No data is stored - stateless proxy
- Ngrok URL changes on restart (unless you have a paid plan with custom domains)
