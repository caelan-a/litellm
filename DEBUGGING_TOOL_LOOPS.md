# Debugging Tool Loops - Investigation Guide

## New Logging Commands

```bash
# View last 5 Cursor requests
make logs-cursor

# Watch requests in real-time
make logs-cursor-watch

# Clear logs and start fresh
make logs-cursor-clear

# View proxy container logs
make logs
make logs-follow
```

## Log Files

- `logs/cursor_requests.jsonl` - Full Cursor API requests/responses (one JSON per line)
- Each log entry includes:
  - Full request (headers, body, messages, tools)
  - Full response (choices, finish_reason, tool_calls)
  - Timing information
  - Request ID for tracking

## How to Debug Tool Loops

### 1. Start Fresh
```bash
make logs-cursor-clear
```

### 2. Reproduce the Issue in Cursor
- Use Cursor with a task that requires tools
- Let it loop a few times

### 3. Inspect the Logs
```bash
make logs-cursor
```

### 4. What to Look For

#### A. Check finish_reason in each response:
```json
{
  "response": {
    "body": {
      "choices": [{
        "finish_reason": "tool_calls"  // Should be this when model wants tools
        // OR
        "finish_reason": "stop"        // Should be this when model is done
      }]
    }
  }
}
```

#### B. Check tool_calls structure:
```json
{
  "choices": [{
    "message": {
      "tool_calls": [{
        "id": "call_xxx",           // Must have ID
        "type": "function",
        "function": {
          "name": "function_name",  // Must have name
          "arguments": "{...}"      // Must be valid JSON string
        }
      }]
    }
  }]
}
```

#### C. Check tool results in next request:
```json
{
  "messages": [
    {"role": "user", "content": "..."},
    {
      "role": "assistant", 
      "content": null,
      "tool_calls": [...]  // The tool call from previous response
    },
    {
      "role": "tool",           // Tool result from Cursor
      "tool_call_id": "call_xxx",  // MUST match the tool call ID
      "content": "result"
    }
  ]
}
```

## Known Issues to Check

### Issue 1: Missing tool_call_id
**Symptom:** Model keeps requesting same tool  
**Cause:** Tool results don't have matching `tool_call_id`  
**Fix:** Check logs for tool_call_id mismatch

### Issue 2: Wrong finish_reason
**Symptom:** Cursor thinks model is done but it's not (or vice versa)  
**Cause:** finish_reason not properly translated from Anthropic  
**Fix:** Check `finish_reason` in logs - should be "tool_calls" or "stop"

### Issue 3: Malformed tool_calls
**Symptom:** Cursor can't execute tools  
**Cause:** tool_calls array format incorrect  
**Fix:** Check tool_calls structure matches OpenAI format

### Issue 4: content field issues
**Symptom:** Empty responses or missing tool call results  
**Cause:** Anthropic returns different structure than OpenAI expects  
**Fix:** Check both `content` and `tool_calls` fields

## Investigation Steps

1. **Capture a full loop cycle** (3-4 requests)
```bash
make logs-cursor-watch  # Keep this running
# Use Cursor until it loops 3-4 times
# Ctrl+C to stop
```

2. **Extract the conversation**
```bash
# View all requests
cat logs/cursor_requests.jsonl | python3 -m json.tool > full_conversation.json
```

3. **Analyze the pattern**
- Request 1: Initial query + tools → Response: tool_calls
- Request 2: Original + assistant message + tool results → Response: ??
- Request 3: Is this a repeat? Check if messages are growing or stuck

4. **Compare with working case**
- Test the same query via direct Anthropic API
- Compare the finish_reason and message structure

## Quick Test

Test tool calling to see if it completes properly:

```bash
curl -s https://mathias-unrelayed-scribbly.ngrok-free.dev/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "claude-sonnet-4.5",
    "messages": [
      {"role": "user", "content": "What is 2+2?"},
      {"role": "assistant", "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "calc", "arguments": "{\"expr\":\"2+2\"}"}}]},
      {"role": "tool", "tool_call_id": "call_1", "content": "4"}
    ],
    "max_tokens": 50
  }' | jq '.choices[0]'
```

Should return `finish_reason: "stop"` and final answer.
