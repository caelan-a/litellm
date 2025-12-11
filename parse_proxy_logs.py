#!/usr/bin/env python3
"""
Parse LiteLLM proxy logs to extract and display API request/response cycles.
Run: python3 parse_proxy_logs.py
"""
import subprocess
import sys
import json
import re
from datetime import datetime


def tail_logs():
    """Tail Docker logs and parse them."""
    cmd = ["docker-compose", "-f", "docker-compose.vertex-claude.yml", "logs", "-f", "litellm-proxy"]
    
    print("🔍 Watching proxy logs for API requests/responses...")
    print("━" * 80)
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    current_request = None
    
    try:
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            
            # Look for POST /v1/chat/completions requests
            if "POST /v1/chat/completions" in line:
                if "200 OK" in line or "400 Bad Request" in line:
                    # Response line
                    status = "✅ 200 OK" if "200 OK" in line else "❌ 400 Bad Request"
                    print(f"\n{status}")
                    print("━" * 80)
                else:
                    # New request starting
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"\n\n📨 NEW REQUEST at {timestamp}")
                    print("━" * 80)
            
            # Look for debug messages
            elif "[DEBUG" in line:
                # Extract the debug message
                match = re.search(r'\[DEBUG[^\]]*\](.*)', line)
                if match:
                    debug_msg = match.group(1).strip()
                    
                    # Highlight important events
                    if "Tools present" in debug_msg:
                        print(f"🔧 {debug_msg}")
                    elif "DISABLING thinking" in debug_msg:
                        print(f"🧠 {debug_msg}")
                    elif "ENABLED THINKING" in debug_msg:
                        print(f"💡 {debug_msg}")
                    elif "Stripping thinking" in debug_msg:
                        print(f"✂️  {debug_msg}")
                    elif "finish_reason" in debug_msg:
                        print(f"🏁 {debug_msg}")
                    elif "tool_choice" in debug_msg or "tool_call" in debug_msg:
                        print(f"🔨 {debug_msg}")
                    else:
                        print(f"   {debug_msg}")
            
            # Look for errors
            elif "ERROR" in line or "BadRequestError" in line:
                if "thinking" in line.lower():
                    print(f"❌ ERROR: {line}")
                elif "tool_choice" in line.lower():
                    print(f"❌ ERROR: {line}")
    
    except KeyboardInterrupt:
        print("\n\n👋 Stopped watching logs")
        process.kill()


if __name__ == "__main__":
    try:
        tail_logs()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
