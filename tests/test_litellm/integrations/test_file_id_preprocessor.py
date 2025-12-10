import pytest

import litellm
from litellm.integrations.file_id_preprocessor import FileIdPreprocessor
from litellm.utils import async_pre_call_deployment_hook


@pytest.fixture
def restore_callbacks():
    original_callbacks = list(litellm.callbacks)
    try:
        yield
    finally:
        litellm.callbacks = original_callbacks


@pytest.mark.asyncio
async def test_file_id_preprocessor_single_value(restore_callbacks):
    preprocessor = FileIdPreprocessor(required_prefix="file_", normalizer=lambda v: v.strip())
    litellm.callbacks = [preprocessor]

    kwargs = {"file_id": " 123 ", "model": "gpt-test"}

    result = await async_pre_call_deployment_hook(kwargs, "completion")

    assert result["file_id"] == "file_123"


@pytest.mark.asyncio
async def test_file_id_preprocessor_multiple_values(restore_callbacks):
    preprocessor = FileIdPreprocessor(required_prefix="file-", normalizer=lambda v: v.strip())
    litellm.callbacks = [preprocessor]

    kwargs = {"file_ids": [" file-1 ", "file-2", " 3 "], "model": "gpt-test"}

    result = await async_pre_call_deployment_hook(kwargs, "completion")

    assert result["file_ids"] == ["file-1", "file-2", "file-3"]
