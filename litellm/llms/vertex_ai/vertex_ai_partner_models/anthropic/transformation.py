# What is this?
## Handler file for calling claude-3 on vertex ai
from typing import Any, List, Optional

import httpx

import litellm
from litellm.llms.base_llm.chat.transformation import LiteLLMLoggingObj
from litellm.types.llms.openai import AllMessageValues
from litellm.types.utils import ModelResponse

from ....anthropic.chat.transformation import AnthropicConfig


class VertexAIError(Exception):
    def __init__(self, status_code, message):
        self.status_code = status_code
        self.message = message
        self.request = httpx.Request(
            method="POST", url=" https://cloud.google.com/vertex-ai/"
        )
        self.response = httpx.Response(status_code=status_code, request=self.request)
        super().__init__(
            self.message
        )  # Call the base class constructor with the parameters it needs


class VertexAIAnthropicConfig(AnthropicConfig):
    """
    Reference:https://docs.anthropic.com/claude/reference/messages_post

    Note that the API for Claude on Vertex differs from the Anthropic API documentation in the following ways:

    - `model` is not a valid parameter. The model is instead specified in the Google Cloud endpoint URL.
    - `anthropic_version` is a required parameter and must be set to "vertex-2023-10-16".

    The class `VertexAIAnthropicConfig` provides configuration for the VertexAI's Anthropic API interface. Below are the parameters:

    - `max_tokens` Required (integer) max tokens,
    - `anthropic_version` Required (string) version of anthropic for bedrock - e.g. "bedrock-2023-05-31"
    - `system` Optional (string) the system prompt, conversion from openai format to this is handled in factory.py
    - `temperature` Optional (float) The amount of randomness injected into the response
    - `top_p` Optional (float) Use nucleus sampling.
    - `top_k` Optional (int) Only sample from the top K options for each subsequent token
    - `stop_sequences` Optional (List[str]) Custom text sequences that cause the model to stop generating

    Note: Please make sure to modify the default parameters as required for your use case.
    """

    @property
    def custom_llm_provider(self) -> Optional[str]:
        return "vertex_ai"

    # Beta flags that are known to be supported by Vertex AI Claude
    # Other beta flags (prompt-caching, effort, files-api, etc.) are NOT supported
    VERTEX_SUPPORTED_BETAS = {
        "tool-search-tool-2025-10-19",  # Tool search
        "web-search-2025-03-05",         # Web search
        "computer-use-2024-10-22",       # Computer use
        "computer-use-2025-01-24",       # Computer use (newer version)
    }

    def _sanitize_tool_choice(self, optional_params: dict) -> dict:
        """
        Sanitize tool_choice parameter to handle invalid values from clients like Cursor.
        
        Cursor sometimes sends tool_choice={'type': 'tool'} without the required 'name' field.
        Anthropic requires tool_choice.tool.name when type is 'tool'.
        
        This method drops invalid tool_choice values to prevent API errors.
        """
        tool_choice = optional_params.get("tool_choice")
        if tool_choice is None:
            return optional_params
        
        # If tool_choice is a dict with type='tool' but missing tool.name, drop it
        if isinstance(tool_choice, dict):
            tc_type = tool_choice.get("type")
            if tc_type == "tool":
                # Check if 'tool' or 'name' is present and valid
                tool_info = tool_choice.get("tool", {})
                if not isinstance(tool_info, dict) or not tool_info.get("name"):
                    # Invalid tool_choice - drop it
                    import sys
                    print(f"[DEBUG _sanitize_tool_choice] Dropping invalid tool_choice: {tool_choice}", file=sys.stderr)
                    optional_params = optional_params.copy()
                    optional_params.pop("tool_choice", None)
        
        return optional_params

    def _is_already_anthropic_format(self, messages: List[AllMessageValues]) -> bool:
        """
        Check if messages are already in Anthropic format (not OpenAI format).
        
        Anthropic format has content as a list with types like 'tool_use', 'tool_result', 'text'.
        OpenAI format has tool_calls as a separate field and tool role messages.
        """
        for msg in messages:
            content = msg.get("content")
            # Check if content is a list (Anthropic format indicator)
            if isinstance(content, list) and len(content) > 0:
                for item in content:
                    if isinstance(item, dict):
                        item_type = item.get("type", "")
                        # These are Anthropic-specific content types
                        if item_type in ("tool_use", "tool_result", "thinking"):
                            return True
        return False
    
    def _strip_thinking_from_messages(self, messages: List[AllMessageValues]) -> List[AllMessageValues]:
        """
        Strip thinking blocks from assistant messages.
        
        This is needed when tools are present, as Vertex AI Claude does not allow
        thinking blocks in assistant messages when thinking is disabled.
        """
        import sys
        cleaned_messages = []
        
        for msg in messages:
            if msg.get("role") != "assistant":
                cleaned_messages.append(msg)
                continue
            
            content = msg.get("content")
            
            # If content is a list, filter out thinking blocks
            if isinstance(content, list):
                filtered_content = []
                has_thinking = False
                
                for item in content:
                    if isinstance(item, dict):
                        item_type = item.get("type", "")
                        if item_type in ("thinking", "redacted_thinking"):
                            has_thinking = True
                            print(f"[DEBUG _strip_thinking_from_messages] Stripping thinking block from assistant message", file=sys.stderr)
                            continue  # Skip thinking blocks
                    filtered_content.append(item)
                
                # Create new message with filtered content
                if has_thinking:
                    new_msg = msg.copy()
                    new_msg["content"] = filtered_content if filtered_content else ""
                    cleaned_messages.append(new_msg)
                else:
                    cleaned_messages.append(msg)
            else:
                # String content - no thinking blocks to strip
                cleaned_messages.append(msg)
        
        return cleaned_messages

    def transform_request(
        self,
        model: str,
        messages: List[AllMessageValues],
        optional_params: dict,
        litellm_params: dict,
        headers: dict,
    ) -> dict:
        # Sanitize tool_choice before calling parent transform
        optional_params = self._sanitize_tool_choice(optional_params)
        
        # IMPORTANT: If tools are present, strip thinking blocks from assistant messages
        # Vertex AI doesn't allow thinking content in assistant messages when thinking is disabled
        tools = optional_params.get("tools")
        if tools and len(tools) > 0:
            import sys
            print(f"[DEBUG transform_request] Tools present - stripping thinking blocks from messages", file=sys.stderr)
            messages = self._strip_thinking_from_messages(messages)
        
        # DEBUG: Log the ORIGINAL messages BEFORE transformation to see what Cursor sends
        import sys
        print(f"[DEBUG BEFORE TRANSFORM] Message count: {len(messages)}", file=sys.stderr)
        
        # Check if messages are already in Anthropic format
        is_anthropic_format = self._is_already_anthropic_format(messages)
        print(f"[DEBUG] Messages already in Anthropic format: {is_anthropic_format}", file=sys.stderr)
        
        for idx, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content")
            tool_calls = msg.get("tool_calls")
            tool_call_id = msg.get("tool_call_id")
            
            content_desc = ""
            if content is None:
                content_desc = "content=None"
            elif isinstance(content, str):
                content_desc = f"content=str({len(content)} chars)"
            elif isinstance(content, list):
                types = [c.get("type") if isinstance(c, dict) else type(c).__name__ for c in content]
                content_desc = f"content=list({types})"
            
            extra = ""
            if tool_calls:
                tc_names = [tc.get("function", {}).get("name", "?") for tc in tool_calls]
                extra += f", tool_calls={tc_names}"
            if tool_call_id:
                extra += f", tool_call_id={tool_call_id}"
                
            print(f"[DEBUG BEFORE TRANSFORM] Msg[{idx}]: role={role}, {content_desc}{extra}", file=sys.stderr)
        
        # If messages are already in Anthropic format, skip the OpenAI->Anthropic transformation
        if is_anthropic_format:
            print(f"[DEBUG] SKIPPING anthropic_messages_pt() - messages already in Anthropic format", file=sys.stderr)
            # Still need to process other parameters
            from litellm.litellm_core_utils.prompt_templates.factory import anthropic_messages_pt
            
            # Separate system messages
            anthropic_system_message_list = self.translate_system_message(messages=messages)
            if len(anthropic_system_message_list) > 0:
                optional_params["system"] = anthropic_system_message_list
            
            # Use messages as-is (already in Anthropic format)
            anthropic_messages = [msg for msg in messages if msg.get("role") != "system"]
            
            # Continue with rest of parent class logic (tools, config, etc.)
            _tools = optional_params.get("tools", []) or []
            tools = self.add_code_execution_tool(messages=anthropic_messages, tools=_tools)
            if len(tools) > 0:
                optional_params["tools"] = tools
            
            config = litellm.AnthropicConfig.get_config()
            for k, v in config.items():
                if k not in optional_params:
                    optional_params[k] = v
            
            _litellm_metadata = litellm_params.get("metadata", None)
            if _litellm_metadata and isinstance(_litellm_metadata, dict):
                user_id = _litellm_metadata.get("user_id", None)
                if user_id:
                    optional_params["metadata"] = {"user_id": user_id}
            
            data = {
                "model": model,
                "messages": anthropic_messages,
                **optional_params,
            }
        else:
            # Normal OpenAI->Anthropic transformation
            data = super().transform_request(
                model=model,
                messages=messages,
                optional_params=optional_params,
                litellm_params=litellm_params,
                headers=headers,
            )

        # DEBUG: Log the transformed messages structure
        import sys
        transformed_messages = data.get("messages", [])
        print(f"[DEBUG AFTER TRANSFORM] Message count: {len(transformed_messages)}", file=sys.stderr)
        
        # Check for consecutive assistant messages (invalid for Anthropic)
        consecutive_assistant_count = 0
        for idx, msg in enumerate(transformed_messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", [])
            content_types = []
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict):
                        content_types.append(c.get("type", "unknown"))
                    else:
                        content_types.append("str")
            elif isinstance(content, str):
                content_types = ["text"]
            
            # Track consecutive assistant messages
            if role == "assistant":
                consecutive_assistant_count += 1
            else:
                if consecutive_assistant_count > 1:
                    print(f"[ERROR] Found {consecutive_assistant_count} consecutive assistant messages before message {idx}", file=sys.stderr)
                consecutive_assistant_count = 0
            
            print(f"[DEBUG AFTER TRANSFORM] Msg[{idx}]: role={role}, content_types={content_types}", file=sys.stderr)

        data.pop("model", None)  # vertex anthropic doesn't accept 'model' parameter
        
        # Also remove invalid tool_choice from the final request data
        if "tool_choice" in data:
            tc = data.get("tool_choice")
            if isinstance(tc, dict) and tc.get("type") == "tool":
                tool_info = tc.get("tool", {})
                if not isinstance(tool_info, dict) or not tool_info.get("name"):
                    import sys
                    print(f"[DEBUG transform_request] Removing invalid tool_choice from data: {tc}", file=sys.stderr)
                    data.pop("tool_choice", None)
        
        # Extended thinking for Vertex AI Claude models
        # Only enable thinking when explicitly requested by the client
        import sys
        
        # IMPORTANT: Disable thinking when tools are present
        # Thinking interferes with tool calling in agent mode, causing infinite loops
        tools = optional_params.get("tools")
        if tools and len(tools) > 0:
            print(f"[DEBUG transform_request] Tools present ({len(tools)} tools) - DISABLING thinking for agent mode compatibility", file=sys.stderr)
            # Don't enable thinking when tools are involved
            thinking_requested = False
        else:
            # Check if thinking is explicitly requested via:
            # 1. Model name contains "thinking" (e.g., claude-4.5-sonnet-thinking)
            # 2. anthropic-beta header contains "thinking" or "interleaved-thinking"
            # 3. thinking parameter is already set in the request
            thinking_requested = False
            
            # Get the original model name requested by the user (before mapping to actual model)
            original_model = litellm_params.get("model", model)
            # Also check proxy_server_request for the original model name from the API request
            proxy_request = litellm_params.get("proxy_server_request", {})
            if proxy_request:
                body = proxy_request.get("body", {})
                if body and isinstance(body, dict):
                    original_model = body.get("model", original_model)
            
            print(f"[DEBUG transform_request] Original model: {original_model}, Mapped model: {model}", file=sys.stderr)
            
            # Check model name for "thinking"
            if "thinking" in original_model.lower():
                thinking_requested = True
                print(f"[DEBUG transform_request] Thinking requested via model name: {original_model}", file=sys.stderr)
            
            # Check headers for anthropic-beta with thinking
            anthropic_beta = headers.get("anthropic-beta", "") or ""
            if isinstance(anthropic_beta, list):
                anthropic_beta = ",".join(anthropic_beta)
            if "thinking" in anthropic_beta.lower() or "interleaved-thinking" in anthropic_beta.lower():
                thinking_requested = True
                print(f"[DEBUG transform_request] Thinking requested via anthropic-beta header: {anthropic_beta}", file=sys.stderr)
            
            # Check if thinking is already set in the request
            if "thinking" in data:
                thinking_requested = True
                print(f"[DEBUG transform_request] Thinking already configured in request", file=sys.stderr)
        
        # Only enable thinking if:
        # 1. It's explicitly requested
        # 2. AND either it's the first turn OR previous assistant messages have thinking blocks
        if thinking_requested and "thinking" not in data:
            # Check if this is a multi-turn conversation and if previous assistant messages have thinking blocks
            previous_assistant_messages = [
                msg for msg in messages[:-1] if msg.get("role") == "assistant"
            ]
            
            # Check if all previous assistant messages have thinking content
            # Vertex AI requires assistant messages to start with thinking blocks when thinking is enabled
            can_enable_thinking = True
            if previous_assistant_messages:
                for msg in previous_assistant_messages:
                    content = msg.get("content", "")
                    # Check if content is structured (list with thinking blocks) or has thinking_blocks field
                    has_thinking = False
                    
                    # Check for thinking_blocks field (OpenAI extension)
                    if msg.get("thinking_blocks"):
                        has_thinking = True
                    # Check for structured content with thinking type
                    elif isinstance(content, list):
                        has_thinking = any(
                            isinstance(c, dict) and c.get("type") in ("thinking", "redacted_thinking")
                            for c in content
                        )
                    
                    if not has_thinking:
                        can_enable_thinking = False
                        print(f"[DEBUG transform_request] Previous assistant message missing thinking blocks", file=sys.stderr)
                        break
            
            if not can_enable_thinking:
                print(f"[DEBUG transform_request] SKIPPING THINKING - previous assistant messages don't have thinking blocks", file=sys.stderr)
            else:
                # First turn OR multi-turn with thinking blocks preserved - enable thinking
                max_tokens_value = data.get("max_tokens", 8000)
                
                # Set thinking budget to 50% of max_tokens
                thinking_budget = int(max_tokens_value * 0.5)
                thinking_budget = max(thinking_budget, 1024)  # Minimum 1024 tokens (Vertex AI requirement)
                thinking_budget = min(thinking_budget, max_tokens_value - 100)  # Leave room for response
                
                data["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": thinking_budget
                }
                if previous_assistant_messages:
                    print(f"[DEBUG transform_request] ENABLED THINKING - multi-turn with thinking blocks preserved (budget: {thinking_budget})", file=sys.stderr)
                else:
                    print(f"[DEBUG transform_request] ENABLED THINKING - first turn (budget: {thinking_budget}, max_tokens: {max_tokens_value})", file=sys.stderr)
        elif not thinking_requested:
            print(f"[DEBUG transform_request] No thinking requested - using standard response", file=sys.stderr)
        
        tools = optional_params.get("tools")
        tool_search_used = self.is_tool_search_used(tools)
        computer_tool_used = self.is_computer_tool_used(tools)
        web_search_tool_used = self.is_web_search_tool_used(tools)
        
        # Only add betas that are specifically supported by Vertex AI
        # Do NOT use get_anthropic_beta_list() as it includes betas not supported by Vertex
        beta_set = set()
        
        if tool_search_used:
            beta_set.add("tool-search-tool-2025-10-19")
        
        if computer_tool_used:
            beta_header = self.get_computer_tool_beta_header(computer_tool_used)
            if beta_header in self.VERTEX_SUPPORTED_BETAS:
                beta_set.add(beta_header)
        
        if web_search_tool_used:
            beta_set.add("web-search-2025-03-05")

        # DEBUG: Log what betas are being added to request body for Vertex
        import sys
        print(f"[DEBUG VertexAIAnthropicConfig.transform_request] model={model}", file=sys.stderr)
        print(f"[DEBUG VertexAIAnthropicConfig.transform_request] tool_search_used={tool_search_used}", file=sys.stderr)
        print(f"[DEBUG VertexAIAnthropicConfig.transform_request] computer_tool_used={computer_tool_used}", file=sys.stderr)
        print(f"[DEBUG VertexAIAnthropicConfig.transform_request] web_search_tool_used={web_search_tool_used}", file=sys.stderr)
        print(f"[DEBUG VertexAIAnthropicConfig.transform_request] beta_set={beta_set}", file=sys.stderr)

        if beta_set:
            data["anthropic_beta"] = list(beta_set)
            print(f"[DEBUG VertexAIAnthropicConfig.transform_request] Added to request body: anthropic_beta={list(beta_set)}", file=sys.stderr)
        else:
            print(f"[DEBUG VertexAIAnthropicConfig.transform_request] NO betas added to request body", file=sys.stderr)
        
        return data

    def transform_response(
        self,
        model: str,
        raw_response: httpx.Response,
        model_response: ModelResponse,
        logging_obj: LiteLLMLoggingObj,
        request_data: dict,
        messages: List[AllMessageValues],
        optional_params: dict,
        litellm_params: dict,
        encoding: Any,
        api_key: Optional[str] = None,
        json_mode: Optional[bool] = None,
    ) -> ModelResponse:
        response = super().transform_response(
            model,
            raw_response,
            model_response,
            logging_obj,
            request_data,
            messages,
            optional_params,
            litellm_params,
            encoding,
            api_key,
            json_mode,
        )
        response.model = model

        # Fix for extended thinking: when thinking is enabled, Vertex AI returns
        # content in reasoning_content but sets content=null. 
        # For OpenAI compatibility, we need to populate content field.
        if response.choices and len(response.choices) > 0:
            for choice in response.choices:
                if hasattr(choice, 'message') and choice.message:
                    msg = choice.message
                    # If content is null/empty but reasoning_content exists, copy it to content
                    if (not msg.content or msg.content == "") and hasattr(msg, 'reasoning_content') and msg.reasoning_content:
                        import sys
                        print(f"[DEBUG transform_response] Copying reasoning_content to content for OpenAI compatibility", file=sys.stderr)
                        msg.content = msg.reasoning_content

        return response

    @classmethod
    def is_supported_model(cls, model: str, custom_llm_provider: str) -> bool:
        """
        Check if the model is supported by the VertexAI Anthropic API.
        """
        if (
            custom_llm_provider != "vertex_ai"
            and custom_llm_provider != "vertex_ai_beta"
        ):
            return False
        if "claude" in model.lower():
            return True
        elif model in litellm.vertex_anthropic_models:
            return True
        return False
