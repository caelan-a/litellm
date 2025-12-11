#!/bin/bash
# Quick HTTPS setup with Cloudflare Tunnel

echo "🔒 Setting up HTTPS with Cloudflare Tunnel..."
echo ""

gcloud compute ssh litellm-proxy-vm --zone=us-east5-a -- 'bash -s' << 'REMOTE'
  set -e
  
  echo "📥 Installing cloudflared..."
  curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
  sudo dpkg -i cloudflared.deb
  rm cloudflared.deb
  
  echo "🚀 Starting Cloudflare Tunnel..."
  # Kill existing tunnel if any
  pkill -f cloudflared || true
  
  nohup cloudflared tunnel --url http://localhost:45678 > /tmp/cloudflare-tunnel.log 2>&1 &
  
  echo "⏳ Waiting for tunnel to start..."
  sleep 5
  
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "✅ HTTPS Tunnel Active!"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  grep -m1 "https://" /tmp/cloudflare-tunnel.log | sed 's/.*\(https:\/\/[^ ]*\).*/Your HTTPS URL: \1/'
  echo ""
  echo "For Cursor:"
  echo "  Base URL: [HTTPS_URL]/v1"
  echo "  API Key: (same as before)"
  echo ""
  echo "📝 Note: This URL will change if the tunnel restarts."
  echo "    For a permanent URL, see HTTPS_SETUP.md"
  echo ""
REMOTE

echo ""
echo "To view tunnel logs:"
echo "  gcloud compute ssh litellm-proxy-vm --zone=us-east5-a -- 'tail -f /tmp/cloudflare-tunnel.log'"
echo ""
