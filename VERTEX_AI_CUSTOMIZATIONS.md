# Vertex AI Claude Customizations

This document describes the key customizations made to the base LiteLLM codebase to enable robust Vertex AI Claude integration with full tool calling support and Cursor compatibility.

## Overview

We've created a custom LiteLLM proxy that bridges Vertex AI's Anthropic Claude models with OpenAI-compatible clients like Cursor. The customizations handle format translation, thinking mode, tool calling, and client-specific quirks.

---

## 🔧 Core Customizations

### 1. Anthropic Format Detection & Pass-Through

**File:** `litellm/llms/vertex_ai/vertex_ai_partner_models/anthropic/transformation.py`

**Problem:** Cursor sends messages in **Anthropic native format** (with `tool_use` and `tool_result` content blocks), but LiteLLM's transformation pipeline was designed for OpenAI format. Running already-Anthropic-formatted messages through `anthropic_messages_pt()` destroyed the tool blocks and caused infinite loops.

**Solution:** 
```python
def _is_already_anthropic_format(self, messages: List[AllMessageValues]) -> bool:
    """Detect if messages already contain Anthropic-specific content types"""
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") in ("tool_use", "tool_result", "thinking"):
                        return True
    return False
```

When Anthropic format is detected, we **skip the OpenAI→Anthropic transformation** and pass messages through as-is, preserving tool blocks intact.

**Impact:** 
- ✅ Tool calling works correctly with Cursor
- ✅ No more infinite loops from mangled tool messages
- ✅ Supports both OpenAI and Anthropic format clients

---

### 2. Thinking Block Stripping for Tool Calls

**File:** `litellm/llms/vertex_ai/vertex_ai_partner_models/anthropic/transformation.py`

**Problem:** When tools are present, Vertex AI requires thinking to be disabled. But Cursor sometimes sends conversation history with thinking blocks from previous turns, causing:
```
messages.3.content.0: When thinking is disabled, an assistant message 
cannot contain thinking.
```

**Solution:**
```python
def _strip_thinking_from_messages(self, messages: List[AllMessageValues]) -> List[AllMessageValues]:
    """Strip thinking blocks from assistant messages when tools are present"""
    cleaned_messages = []
    for msg in messages:
        if msg.get("role") != "assistant":
            cleaned_messages.append(msg)
            continue
        
        content = msg.get("content")
        if isinstance(content, list):
            filtered_content = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") in ("thinking", "redacted_thinking"):
                        continue  # Skip thinking blocks
                filtered_content.append(item)
            
            new_msg = msg.copy()
            new_msg["content"] = filtered_content if filtered_content else ""
            cleaned_messages.append(new_msg)
        else:
            cleaned_messages.append(msg)
    
    return cleaned_messages
```

**Applied when:** Tools are detected in the request.

**Impact:**
- ✅ Prevents API errors from thinking/tool conflicts
- ✅ Preserves conversation continuity
- ✅ Allows thinking mode when tools are not involved

---

### 3. Invalid `tool_choice` Sanitization

**File:** `litellm/llms/vertex_ai/vertex_ai_partner_models/anthropic/transformation.py`

**Problem:** Cursor sometimes sends:
```json
{"tool_choice": {"type": "tool"}}  // Missing required 'name' field
```

Anthropic requires `tool_choice.tool.name` when `type='tool'`, causing:
```
tool_choice.tool.name: Field required
```

**Solution:**
```python
def _sanitize_tool_choice(self, optional_params: dict) -> dict:
    """Drop invalid tool_choice parameters from clients like Cursor"""
    tool_choice = optional_params.get("tool_choice")
    if tool_choice is None:
        return optional_params
    
    if isinstance(tool_choice, dict):
        if tool_choice.get("type") == "tool":
            tool_info = tool_choice.get("tool", {})
            if not isinstance(tool_info, dict) or not tool_info.get("name"):
                # Invalid - drop it
                optional_params = optional_params.copy()
                optional_params.pop("tool_choice", None)
    
    return optional_params
```

**Impact:**
- ✅ Prevents errors from malformed tool_choice
- ✅ Falls back to auto tool selection (Claude decides which tools to use)

---

### 4. Conditional Thinking Mode

**File:** `litellm/llms/vertex_ai/vertex_ai_partner_models/anthropic/transformation.py`

**Logic:**
```python
tools = optional_params.get("tools")
if tools and len(tools) > 0:
    # DISABLE thinking when tools are present (agent mode)
    thinking_requested = False
else:
    # CHECK if thinking is requested via:
    # 1. Model name contains "thinking" (e.g., claude-4.5-sonnet-thinking)
    # 2. anthropic-beta header contains "thinking"
    # 3. thinking parameter already set
```

**Why:** Thinking mode interferes with tool calling in agent workflows. We automatically disable it when tools are detected.

**Impact:**
- ✅ Reliable tool calling without thinking conflicts
- ✅ Thinking still available for non-tool use cases
- ✅ Transparent to end users

---

## 🐳 Docker Hot Reload Setup

**Files:** 
- `docker-compose.vertex-claude.yml`
- `Dockerfile.custom`

**Key Innovation:** Volume-mounted source code for instant updates without rebuilding:

```yaml
volumes:
  - ./litellm:/app/litellm:ro  # Mount source for hot reload
  - ./litellm_vertex_claude_config.yaml:/app/config.yaml:ro
  - ./logs:/app/logs  # Persist logs to host
```

**Benefits:**
- ⚡ Code changes take effect with just `make restart` (no rebuild)
- 🔍 Easy debugging with live log inspection
- 🚀 Faster iteration during development

---

## 📊 Comprehensive Logging

**Added Debug Logging:**

```python
# BEFORE transformation (see what client sends)
[DEBUG BEFORE TRANSFORM] Message count: 5
[DEBUG BEFORE TRANSFORM] Msg[0]: role=user, content=list(['text'])
[DEBUG BEFORE TRANSFORM] Msg[1]: role=assistant, content=list(['tool_use'])
[DEBUG BEFORE TRANSFORM] Msg[2]: role=user, content=list(['tool_result'])

# AFTER transformation (see what we send to Vertex)
[DEBUG AFTER TRANSFORM] Message count: 3
[DEBUG AFTER TRANSFORM] Msg[0]: role=user, content_types=['text']
[DEBUG AFTER TRANSFORM] Msg[1]: role=assistant, content_types=['tool_use']
[DEBUG AFTER TRANSFORM] Msg[2]: role=user, content_types=['tool_result']

# Thinking detection
[DEBUG] Messages already in Anthropic format: True
[DEBUG] SKIPPING anthropic_messages_pt() - messages already in Anthropic format
```

**Makefile Commands:**
```bash
make logs-watch      # Live parsed logs with highlighting
make logs           # Recent logs
make logs-search pattern="thinking"  # Search logs
```

---

## 🔒 Robust Error Handling

### Fail-Fast Philosophy

Per user requirements: **No fallbacks, fail hard and fast**

```python
# ❌ BAD (silently handles errors)
try:
    result = transform(messages)
except:
    result = messages  # Fallback - hides problems!

# ✅ GOOD (exposes problems immediately)  
result = transform(messages)  # Let it fail so we can fix it
```

**Benefits:**
- Problems surface immediately during development
- No silent data corruption
- Clear error messages for debugging

---

## 📁 Project Structure

```
litellm/
├── litellm/llms/vertex_ai/vertex_ai_partner_models/anthropic/
│   └── transformation.py           # 🔥 Core customizations
├── docker-compose.vertex-claude.yml  # Docker orchestration
├── Dockerfile.custom                 # Custom build with fixes
├── litellm_vertex_claude_config.yaml # Proxy configuration
├── Makefile                          # Easy commands
├── ngrok.yml                         # Tunnel configuration
├── logs/                             # Request logs
└── VERTEX_AI_CUSTOMIZATIONS.md       # This file
```

---

## 🧪 Testing Strategy

### Quick Test (Simple Tool Use)
```bash
curl -s https://YOUR_URL/v1/chat/completions \
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

**Expected:** `finish_reason: "stop"` with final answer

### Integration Test (Cursor)
1. Configure Cursor with proxy URL
2. Ask it to perform a task with tools (e.g., "read this file")
3. Monitor: `make logs-watch`
4. Verify: 
   - No infinite loops
   - Messages preserve `tool_use`/`tool_result` blocks
   - Eventually returns `finish_reason: "stop"`

---

## 🚀 Deployment

### Development (Local with ngrok)
```bash
# Initial setup
make start

# After code changes
make restart  # Uses hot reload

# View logs
make logs-watch
```

### Production Considerations
1. **Remove ngrok** - use proper ingress/load balancer
2. **Add authentication** - currently accepts any API key
3. **Rate limiting** - configure in `litellm_vertex_claude_config.yaml`
4. **Monitoring** - integrate with your observability stack
5. **Secrets management** - use proper secret store for Google credentials

---

## 🔍 Key Differences from Base LiteLLM

| Aspect | Base LiteLLM | Our Customization |
|--------|--------------|-------------------|
| Message Format Detection | Assumes OpenAI format | Detects Anthropic format, skips transform |
| Thinking Mode | Always enabled if requested | Disabled when tools present |
| Tool Choice Validation | Passes through as-is | Sanitizes invalid values |
| Thinking in History | Not handled | Strips from messages when needed |
| Error Handling | Some fallbacks | Fail-fast, no silent failures |
| Development | Rebuild for changes | Hot reload with volumes |
| Logging | Basic | Detailed before/after transform logs |

---

## 🐛 Troubleshooting Guide

### Issue: Tool Loops
**Symptom:** Claude keeps calling same tools repeatedly  
**Check logs for:**
```
[DEBUG AFTER TRANSFORM] Msg[X]: role=assistant, content_types=['text']
```
**Should be:** `content_types=['tool_use']`

**Fix:** Messages are being transformed incorrectly. Check if Anthropic format detection is working.

---

### Issue: Thinking Errors
**Symptom:** `assistant message cannot contain thinking`  
**Check logs for:**
```
[DEBUG] Tools present - stripping thinking blocks from messages
```
**Should appear:** When tools are in the request

**Fix:** Ensure `_strip_thinking_from_messages()` is being called.

---

### Issue: tool_choice Errors
**Symptom:** `tool_choice.tool.name: Field required`  
**Check logs for:**
```
[DEBUG _sanitize_tool_choice] Dropping invalid tool_choice: ...
```
**Should appear:** When malformed tool_choice detected

**Fix:** Sanitization should drop invalid values automatically.

---

## 📚 Related Documentation

- **Setup Guide:** `VERTEX_CLAUDE_SETUP.md` - Getting started
- **Debugging Guide:** `DEBUGGING_TOOL_LOOPS.md` - Tool loop investigation
- **LiteLLM Docs:** https://docs.litellm.ai/
- **Anthropic Docs:** https://docs.anthropic.com/claude/docs/

---

## 🎯 Future Enhancements

### Potential Improvements
1. **Automatic format detection caching** - avoid re-checking on every request
2. **Streaming thinking mode** - support thinking with tools in compatible scenarios
3. **Tool choice auto-correction** - instead of dropping, auto-select first tool
4. **Message validation** - deep validation before sending to Vertex
5. **Metrics & observability** - track transformation decisions, error rates

### Known Limitations
1. **No prompt caching** - Vertex AI doesn't support Anthropic's prompt caching
2. **No extended thinking with tools** - architectural limitation
3. **Single project/region** - config hardcoded to one Vertex AI project

---

## 📝 Maintenance Notes

### When Updating Base LiteLLM

1. **Check transformation.py** - ensure our customizations don't conflict
2. **Test with Cursor** - verify tool calling still works
3. **Review `anthropic_messages_pt()`** - this is the function we bypass
4. **Check new Anthropic features** - may need integration

### Code Ownership

**Modified Files (maintain our changes):**
- `litellm/llms/vertex_ai/vertex_ai_partner_models/anthropic/transformation.py`

**Custom Files (our additions):**
- `docker-compose.vertex-claude.yml`
- `Dockerfile.custom`
- `litellm_vertex_claude_config.yaml`
- `Makefile` (modified)
- `VERTEX_AI_CUSTOMIZATIONS.md` (this file)
- `VERTEX_CLAUDE_SETUP.md`
- `DEBUGGING_TOOL_LOOPS.md`
- `parse_proxy_logs.py`
- `cursor_request_logger.py`

---

## ✅ Success Criteria

A working deployment should:
- ✅ Accept both OpenAI and Anthropic format messages
- ✅ Preserve tool_use/tool_result blocks through transformation
- ✅ Complete tool-calling tasks without infinite loops
- ✅ Disable thinking when tools are present
- ✅ Sanitize invalid tool_choice parameters
- ✅ Return proper finish_reason ('tool_calls' or 'stop')
- ✅ Work seamlessly with Cursor IDE

---

## 🙏 Acknowledgments

This customization builds on the excellent work of:
- **LiteLLM** - Universal LLM interface
- **Anthropic** - Claude API and documentation
- **Google Cloud** - Vertex AI platform
- **Cursor** - The IDE that motivated these fixes

---

**Last Updated:** December 11, 2024  
**Version:** 1.0  
**Status:** Production-ready for Vertex AI Claude with Cursor
