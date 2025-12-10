#!/usr/bin/env python3
"""
Test script for Vertex AI Claude models via LiteLLM proxy.
Run this AFTER starting the proxy to verify the setup works.

Usage:
    python test_vertex_claude.py [--proxy-url http://localhost:4000]
"""

import argparse
import requests
import json


def test_model(proxy_url: str, model: str, api_key: str = "sk-litellm-cursor-proxy"):
    """Test a single model via the proxy."""
    print(f"\n{'='*60}")
    print(f"Testing model: {model}")
    print(f"{'='*60}")
    
    url = f"{proxy_url}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model,
        "messages": [
            {"role": "user", "content": "Say 'Hello from Vertex AI Claude!' and nothing else."}
        ],
        "max_tokens": 50
    }
    
    print(f"Request URL: {url}")
    print(f"Request body: {json.dumps(data, indent=2)}")
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=60)
        print(f"\nResponse status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"✅ SUCCESS!")
            print(f"Response: {content}")
            return True
        else:
            print(f"❌ FAILED")
            print(f"Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ FAILED with exception: {e}")
        return False


def test_streaming(proxy_url: str, model: str, api_key: str = "sk-litellm-cursor-proxy"):
    """Test streaming for a model via the proxy."""
    print(f"\n{'='*60}")
    print(f"Testing STREAMING for model: {model}")
    print(f"{'='*60}")
    
    url = f"{proxy_url}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model,
        "messages": [
            {"role": "user", "content": "Count from 1 to 5, one number per line."}
        ],
        "max_tokens": 50,
        "stream": True
    }
    
    print(f"Request URL: {url}")
    print(f"Streaming: True")
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=60, stream=True)
        print(f"\nResponse status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Streaming response:")
            full_content = ""
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith("data: "):
                        data_str = line_str[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                print(content, end="", flush=True)
                                full_content += content
                        except json.JSONDecodeError:
                            pass
            print("\n")
            return True
        else:
            print(f"❌ FAILED")
            print(f"Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ FAILED with exception: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test Vertex AI Claude via LiteLLM proxy")
    parser.add_argument("--proxy-url", default="http://localhost:4000", help="LiteLLM proxy URL")
    parser.add_argument("--api-key", default="sk-litellm-cursor-proxy", help="API key for proxy")
    parser.add_argument("--model", default=None, help="Specific model to test")
    parser.add_argument("--stream-only", action="store_true", help="Only test streaming")
    args = parser.parse_args()
    
    # Models to test
    models = ["claude-sonnet-4.5", "claude-opus-4.5"] if args.model is None else [args.model]
    
    print(f"LiteLLM Proxy URL: {args.proxy_url}")
    print(f"Models to test: {models}")
    
    # First check if proxy is running
    try:
        health = requests.get(f"{args.proxy_url}/health", timeout=5)
        print(f"\n✅ Proxy is running (health check: {health.status_code})")
    except Exception as e:
        print(f"\n❌ Cannot connect to proxy at {args.proxy_url}")
        print(f"   Make sure the proxy is running!")
        print(f"   Error: {e}")
        return
    
    results = {}
    for model in models:
        if not args.stream_only:
            results[f"{model} (non-streaming)"] = test_model(args.proxy_url, model, args.api_key)
        results[f"{model} (streaming)"] = test_streaming(args.proxy_url, model, args.api_key)
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")


if __name__ == "__main__":
    main()

