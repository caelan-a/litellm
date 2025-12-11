"""
Custom middleware to log all Cursor API requests and responses
Saves detailed logs to /app/logs/cursor_requests.jsonl
"""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse
import os


class CursorRequestLogger(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.log_dir = Path("/app/logs")
        self.log_dir.mkdir(exist_ok=True)
        self.log_file = self.log_dir / "cursor_requests.jsonl"
        
    async def dispatch(self, request: Request, call_next: Callable):
        # Only log chat completions (skip health checks)
        if "/chat/completions" not in str(request.url):
            return await call_next(request)
        
        # Capture request
        request_id = f"req_{int(time.time()*1000)}"
        request_body = None
        
        if request.method == "POST":
            body = await request.body()
            try:
                request_body = json.loads(body.decode())
            except:
                request_body = body.decode()
            
            # Reconstruct request for next middleware
            async def receive():
                return {"type": "http.request", "body": body}
            request._receive = receive
        
        # Call next middleware
        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time
        
        # Capture response (for non-streaming)
        response_body = None
        if not isinstance(response, StreamingResponse):
            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk
            
            try:
                response_data = json.loads(response_body.decode())
            except:
                response_data = response_body.decode()
            
            # Log everything
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "request_id": request_id,
                "duration_seconds": round(duration, 3),
                "request": {
                    "method": request.method,
                    "url": str(request.url),
                    "headers": dict(request.headers),
                    "body": request_body,
                },
                "response": {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response_data,
                }
            }
            
            # Write to log file
            with open(self.log_file, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
            
            # Reconstruct response
            return Response(
                content=response_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )
        
        return response
