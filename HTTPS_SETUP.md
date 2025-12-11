# HTTPS Setup for Cloud VM

Your LiteLLM proxy is currently running on HTTP. Here are your options for HTTPS:

---

## Option 1: Cloudflare Tunnel (Recommended - Free & Easy) ⭐

**Pros:**
- ✅ Free
- ✅ Automatic HTTPS
- ✅ No domain required (gets subdomain like `xyz.trycloudflare.com`)
- ✅ 5 minute setup
- ✅ No firewall changes needed

**Cons:**
- ⚠️ URL changes if tunnel restarts (can use named tunnel for static URL)

### Quick Setup:

```bash
# SSH to VM
gcloud compute ssh litellm-proxy-vm --zone=us-east5-a

# Install cloudflared
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb

# Start tunnel (temporary)
cloudflared tunnel --url http://localhost:45678
```

You'll get output like:
```
https://abc-xyz-123.trycloudflare.com
```

**Use that HTTPS URL in Cursor!**

### Persistent Tunnel (Static URL):

```bash
# 1. Login to Cloudflare
cloudflared tunnel login

# 2. Create named tunnel
cloudflared tunnel create litellm-proxy

# 3. Create config
sudo mkdir -p /etc/cloudflared
sudo nano /etc/cloudflared/config.yml
```

Add:
```yaml
tunnel: litellm-proxy
credentials-file: /root/.cloudflared/YOUR_TUNNEL_ID.json

ingress:
  - hostname: your-subdomain.yourdomain.com  # or use random subdomain
    service: http://localhost:45678
  - service: http_status:404
```

```bash
# 4. Route DNS (if using your domain)
cloudflared tunnel route dns litellm-proxy your-subdomain.yourdomain.com

# 5. Install as service
sudo cloudflared service install
sudo systemctl start cloudflared
sudo systemctl enable cloudflared
```

**Static HTTPS URL:** `https://your-subdomain.yourdomain.com`

---

## Option 2: Caddy (Easiest with Domain)

**Pros:**
- ✅ Automatic HTTPS with Let's Encrypt
- ✅ Simple config
- ✅ Auto-renewal

**Cons:**
- ❌ Requires a domain name

### Setup:

```bash
# SSH to VM
gcloud compute ssh litellm-proxy-vm --zone=us-east5-a

# Install Caddy
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy

# Configure Caddy
sudo nano /etc/caddy/Caddyfile
```

Add:
```
your-domain.com {
    reverse_proxy localhost:45678
}
```

```bash
# Start Caddy
sudo systemctl reload caddy
```

**Point your domain's A record to:** `34.186.232.98`

HTTPS will be automatic!

---

## Option 3: nginx + Let's Encrypt (Traditional)

**Pros:**
- ✅ Industry standard
- ✅ Full control

**Cons:**
- ❌ Requires domain
- ❌ More complex setup
- ❌ Manual renewal setup

### Setup:

```bash
# SSH to VM
gcloud compute ssh litellm-proxy-vm --zone=us-east5-a

# Install nginx and certbot
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx

# Configure nginx
sudo nano /etc/nginx/sites-available/litellm
```

Add:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:45678;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support (for streaming)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/litellm /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Get SSL certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal is automatic with certbot
```

---

## Option 4: Google Cloud Load Balancer

**Pros:**
- ✅ Integrated with GCP
- ✅ DDoS protection
- ✅ Global load balancing

**Cons:**
- ❌ Expensive (~$18/month + traffic costs)
- ❌ Complex setup
- ❌ Overkill for single VM

Not recommended unless you need enterprise features.

---

## Comparison

| Option | Cost | Setup Time | Domain Needed | Static URL |
|--------|------|------------|---------------|------------|
| Cloudflare Tunnel (quick) | Free | 2 min | No | No |
| Cloudflare Tunnel (named) | Free | 10 min | Optional | Yes |
| Caddy | Free | 10 min | Yes | Yes |
| nginx + Let's Encrypt | Free | 20 min | Yes | Yes |
| GCP Load Balancer | ~$18/mo | 30 min | Optional | Yes |

---

## Recommended Setup

### For Immediate Use:
```bash
# Quick Cloudflare tunnel (2 minutes)
gcloud compute ssh litellm-proxy-vm --zone=us-east5-a -- '
  curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
  sudo dpkg -i cloudflared.deb
  nohup cloudflared tunnel --url http://localhost:45678 > /tmp/cloudflare-tunnel.log 2>&1 &
'

# Get the URL
gcloud compute ssh litellm-proxy-vm --zone=us-east5-a -- 'tail -f /tmp/cloudflare-tunnel.log | grep -m1 "https://"'
```

### For Production:
1. Get a domain ($10-15/year)
2. Use Caddy (automatic HTTPS, zero config)
3. Point domain to `34.186.232.98`

---

## Current HTTP Access Still Works

Your HTTP endpoint still works:
- `http://34.186.232.98:45678/v1`

But it's unencrypted. HTTPS is **strongly recommended** for production use.

---

## Security Notes

**Why HTTPS matters:**
- 🔒 Encrypts your API keys in transit
- 🔒 Encrypts your prompts and responses
- 🔒 Prevents man-in-the-middle attacks
- ✅ Required by many clients (browsers, some apps)

**Current Risk (HTTP only):**
- Anyone on the network path can see:
  - Your API key
  - Your prompts to Claude
  - Claude's responses
  - All database operations

**Use HTTPS for anything beyond local testing!**

