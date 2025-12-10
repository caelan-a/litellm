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

    def transform_request(
        self,
        model: str,
        messages: List[AllMessageValues],
        optional_params: dict,
        litellm_params: dict,
        headers: dict,
    ) -> dict:
        data = super().transform_request(
            model=model,
            messages=messages,
            optional_params=optional_params,
            litellm_params=litellm_params,
            headers=headers,
        )

        data.pop("model", None)  # vertex anthropic doesn't accept 'model' parameter
        
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
