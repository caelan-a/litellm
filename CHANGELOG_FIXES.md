# Changelog - Tool Loop & Thinking Fixes

## 🐛 Bug Fixes (Dec 11, 2024)

### Issue: Infinite Tool Calling Loops with Cursor
**Symptom:** When using Cursor with the proxy, the assistant would repeatedly call the same tools in an infinite loop, never completing the task.

**Root Cause:** Cursor uses Claude's "thinking" mode (extended reasoning), which generates thinking blocks in assistant messages. When Cursor sent tool results back with the conversation history, those previous assistant messages still contained thinking blocks. However, when tools are present, our transformation layer correctly disabled thinking mode, but **we weren't stripping the thinking blocks from previous assistant messages**. This caused Vertex AI to reject the request with:

```
messages.3.content.0: When thinking is disabled, an `assistant` message in the 
final position cannot contain `thinking`. To use thinking blocks, enable `thinking` 
in your request.
```

**Fix:** Modified `litellm/llms/vertex_ai/vertex_ai_partner_models/anthropic/transformation.py`:
1. Added `_strip_thinking_from_messages()` method that filters out thinking blocks from assistant messages
2. Called this method in `transform_request()` when tools are present
3. This ensures Vertex AI receives clean messages without thinking blocks when in tool-calling mode

**Code Changes:**
- File: `litellm/llms/vertex_ai/vertex_ai_partner_models/anthropic/transformation.py`
- Added method at line ~91
- Modified `transform_request()` at line ~140

**Result:** Tool calling now works correctly with Cursor. The proxy:
- Strips thinking blocks from conversation history when tools are present
- Disables thinking mode when tools are present
- Allows thinking mode for non-tool interactions
- Properly handles multi-turn conversations with tools

### Secondary Issue: Missing Request Logs
**Symptom:** The custom middleware logging wasn't working; no logs appeared in `logs/cursor_requests.jsonl`.

**Root Cause:** The custom middleware approach via `general_settings.custom_middleware` doesn't work reliably with LiteLLM's proxy configuration.

**Fix:** Created a simpler approach:
1. Enabled `set_verbose: true` in the proxy config for detailed logging
2. Created `parse_proxy_logs.py` - a Python script that tails and parses Docker logs
3. Added `make logs-watch` command for easy log monitoring with intelligent highlighting

**Result:** Easy-to-use log watching:
```bash
make logs-watch  # Watch logs with highlighting
make logs        # View recent logs
make logs-search pattern="thinking"  # Search logs
```

## 🧪 Testing

To verify the fix:

1. **Start the proxy:**
   ```bash
   make restart
   ```

2. **Watch logs in another terminal:**
   ```bash
   make logs-watch
   ```

3. **Use Cursor with complex tool-calling tasks**
   - Example: "Read all files in this directory and create a summary"
   - Should see: ✂️ Stripping thinking blocks from assistant messages
   - Should complete successfully without looping

## 📝 Technical Details

### Why Thinking Blocks Cause Tool Loop Issues

1. **Cursor's Thinking Mode:**
   - Cursor can use Claude's extended reasoning (thinking) mode
   - Thinking blocks allow Claude to reason step-by-step
   - These appear in assistant messages as `{type: "thinking", thinking: "..."}`

2. **Tool Calling Mode:**
   - Tools require focused, deterministic responses
   - Thinking mode interferes with tool calling flow
   - Vertex AI requires either thinking enabled with all messages having thinking, OR thinking disabled with no thinking blocks

3. **The Conflict:**
   - Cursor might request thinking in early turns
   - Later turns with tools need thinking disabled
   - But conversation history contains thinking blocks from earlier
   - Vertex AI rejects mixed mode messages

4. **The Solution:**
   - When tools are present: disable thinking AND strip thinking blocks from history
   - Ensures clean, consistent message format for Vertex AI
   - Preserves thinking mode for non-tool interactions

### Message Transformation Flow

```
Cursor Request (with tools)
  ↓
  messages: [
    {role: "user", content: "..."},
    {role: "assistant", content: [{type: "thinking", ...}, {type: "text", ...}]},  ← Has thinking!
    {role: "tool", ...}
  ]
  ↓
_strip_thinking_from_messages()  ← NEW
  ↓
  messages: [
    {role: "user", content: "..."},
    {role: "assistant", content: [{type: "text", ...}]},  ← Thinking removed
    {role: "tool", ...}
  ]
  ↓
transform_request() (thinking disabled for tools)
  ↓
Vertex AI Request (clean, no thinking)
```

## 🎯 Next Steps

If tool loops still occur:
1. Run `make logs-watch` in a terminal
2. Use Cursor to reproduce the issue
3. Look for:
   - ✂️ Markers showing thinking blocks being stripped
   - 🔧 Markers showing tools detected
   - 🏁 `finish_reason` values (should be "tool_calls" or "stop")
   - ❌ Any errors about thinking or tool_choice

4. Share the log output for further investigation

## 🔗 Related Files

- `litellm/llms/vertex_ai/vertex_ai_partner_models/anthropic/transformation.py` - Main fix
- `parse_proxy_logs.py` - Log parsing utility
- `Makefile` - Easy commands for log viewing
- `docker-compose.vertex-claude.yml` - Docker setup
- `litellm_vertex_claude_config.yaml` - Proxy configuration
