# LiteLLM Admin UI & Persistence Setup

## ⚠️ Current Status

**UI & Database:** ❌ Disabled (requires PostgreSQL)  
**API Works:** ✅ Fully functional  
**Authentication:** ❌ None (accepts any API key for development)

---

## 📋 Two Options for UI & Persistence

### Option 1: No Database (Current Setup) ✅

**What works:**
- ✅ Full API functionality for Cursor
- ✅ All models available
- ✅ Tool calling works perfectly
- ✅ Hot reload for code changes

**What doesn't work:**
- ❌ Admin UI dashboard
- ❌ Usage tracking & analytics
- ❌ Budget limits per key
- ❌ API key management

**Best for:** Development, testing, personal use

---

### Option 2: Full Setup with PostgreSQL (Recommended for Production)

To enable the UI, usage tracking, and persistent budgets, you need PostgreSQL.

#### Quick Setup with Docker Compose

1. **Add PostgreSQL to docker-compose:**

```yaml
# Add to docker-compose.vertex-claude.yml

services:
  # ... existing services ...
  
  postgres:
    image: postgres:15-alpine
    container_name: litellm-postgres
    environment:
      - POSTGRES_DB=litellm
      - POSTGRES_USER=litellm
      - POSTGRES_PASSWORD=litellm_password_change_me
    volumes:
      - ./postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U litellm"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
```

2. **Update litellm-proxy service:**

```yaml
litellm-proxy:
  # ... existing config ...
  environment:
    - GOOGLE_APPLICATION_CREDENTIALS=/app/google-creds.json
    - LITELLM_MASTER_KEY=${LITELLM_MASTER_KEY}
    - DATABASE_URL=postgresql://litellm:litellm_password_change_me@postgres:5432/litellm
  depends_on:
    postgres:
      condition: service_healthy
```

3. **Update config file** (`litellm_vertex_claude_config.yaml`):

```yaml
general_settings:
  database_url: "postgresql://litellm:litellm_password_change_me@postgres:5432/litellm"
  master_key: os.environ/LITELLM_MASTER_KEY
  ui_username: admin
  ui_password: os.environ/LITELLM_MASTER_KEY
```

4. **Restart:**

```bash
make stop-all
make start
```

5. **Access UI:**
- Local: http://localhost:45678/ui
- Public: https://YOUR_NGROK_URL/ui
- Login: admin / YOUR_MASTER_KEY

---

## 🎨 What You Get With PostgreSQL + UI

### 1. **Admin Dashboard**
- Real-time usage statistics
- Cost tracking
- Request rates
- Model distribution

### 2. **API Key Management**
- Generate keys for different users/apps
- Set per-key budgets ($10/month, etc.)
- Set rate limits (60 req/min, etc.)
- Enable/disable keys instantly

### 3. **Usage Tracking**
- Track spend by key
- Token usage statistics
- Export usage reports (CSV)
- Historical data

### 4. **Budget Controls**
- Global budget limits
- Per-key budget limits
- Auto-suspend when budget exceeded
- Email alerts (when configured)

### 5. **Persistent Data**
All data survives docker restarts:
- ✅ API keys
- ✅ Usage history
- ✅ Budget settings
- ✅ User configurations

---

## 🔑 Without UI: Manual API Key Management

If you don't need the UI, you can still use authentication by setting keys manually:

### In `.env`:
```bash
LITELLM_MASTER_KEY=sk-1234567890abcdef  # Your admin key
```

### In `litellm_vertex_claude_config.yaml`:
```yaml
general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  
# Optional: Pre-create some API keys
virtual_keys:
  - key: sk-cursor-dev-key
    models: ["claude-sonnet-4.5", "claude-opus-4.5"]
    max_budget: 10.00
    budget_duration: "monthly"
    
  - key: sk-production-key
    models: ["claude-opus-4.5"]
    max_budget: 100.00
    budget_duration: "monthly"
```

**Usage:**
```bash
curl https://YOUR_URL/v1/chat/completions \
  -H "Authorization: Bearer sk-cursor-dev-key" \
  -d '{"model": "claude-sonnet-4.5", "messages": [...]}'
```

---

## 💡 Recommendations

### For Development (Current Setup)
- ✅ Keep it simple without database
- ✅ No authentication needed
- ✅ Fast iteration with hot reload
- ✅ Perfect for Cursor integration

### For Team/Production
- ✅ Set up PostgreSQL
- ✅ Enable the UI
- ✅ Create separate keys per developer
- ✅ Set budget limits
- ✅ Track usage and costs
- ✅ Use proper auth (not ngrok)

---

## 📊 Usage Tracking Without UI

Even without the database, you can track usage through logs:

```bash
# Watch real-time requests
make logs-watch

# Search for specific patterns
make logs-search pattern="finish_reason"

# Export logs for analysis
docker-compose -f docker-compose.vertex-claude.yml logs litellm-proxy > usage_log.txt
```

**Parse logs for usage:**
```bash
# Count requests
grep "POST /v1/chat/completions" usage_log.txt | wc -l

# Find token usage
grep "total_tokens" usage_log.txt
```

---

## 🔧 Setting Up PostgreSQL (Detailed Steps)

### Step 1: Create postgres config
```bash
mkdir -p postgres_data
```

### Step 2: Update docker-compose.vertex-claude.yml
Add the postgres service and update litellm-proxy environment as shown above.

### Step 3: Update .env
```bash
# Add to .env
DATABASE_URL=postgresql://litellm:litellm_password_change_me@postgres:5432/litellm
```

### Step 4: Initialize
```bash
docker-compose -f docker-compose.vertex-claude.yml up -d postgres
sleep 5
docker-compose -f docker-compose.vertex-claude.yml up -d litellm-proxy
```

### Step 5: Verify
```bash
# Check if database is accessible
docker-compose -f docker-compose.vertex-claude.yml exec postgres \
  psql -U litellm -d litellm -c "\dt"

# Check UI
curl http://localhost:45678/ui
```

---

## 🐛 Troubleshooting

### Prisma Errors
**Symptom:** `Could not connect to query engine`  
**Fix:** PostgreSQL is required, SQLite not fully supported

### UI Not Loading
**Check:**
1. PostgreSQL is running: `docker-compose ps`
2. Database is initialized: Check logs for "Prisma"
3. Master key is set: `echo $LITELLM_MASTER_KEY`

### Cannot Connect to Database
```bash
# Test connection
docker-compose -f docker-compose.vertex-claude.yml exec litellm-proxy \
  python3 -c "import psycopg2; psycopg2.connect('postgresql://litellm:litellm_password_change_me@postgres:5432/litellm')"
```

---

## 📚 More Information

- **LiteLLM Database Docs:** https://docs.litellm.ai/docs/proxy/virtual_keys
- **LiteLLM UI Docs:** https://docs.litellm.ai/docs/proxy/ui
- **Budget Management:** https://docs.litellm.ai/docs/proxy/users

---

## ✅ Summary

**Current Setup (No Database):**
- ✅ Perfect for development and Cursor
- ✅ No complexity, just works
- ❌ No UI, no usage tracking
- ❌ No budget controls

**With PostgreSQL:**
- ✅ Full UI dashboard
- ✅ Usage tracking & analytics
- ✅ Budget controls
- ✅ Persistent data
- ⚠️ More complex setup

**Choose based on your needs!**

For development with Cursor: Current setup is perfect ✅  
For production/teams: Add PostgreSQL for full features 🚀
