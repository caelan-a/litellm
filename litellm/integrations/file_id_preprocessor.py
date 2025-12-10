from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Iterable, Optional, Union

from litellm.integrations.custom_logger import CustomLogger

if TYPE_CHECKING:
    from litellm.types.utils import CallTypes


StringNormalizer = Callable[[str], str]


class FileIdPreprocessor(CustomLogger):
    """
    Normalize file identifiers right before a deployment is invoked.
    Attach an instance to `litellm.callbacks` or pass via the `callbacks`
    kwarg to enable the preprocessing behaviour.
    """

    def __init__(
        self,
        *,
        required_prefix: Optional[str] = None,
        normalizer: Optional[StringNormalizer] = None,
        turn_off_message_logging: bool = False,
        message_logging: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(
            turn_off_message_logging=turn_off_message_logging,
            message_logging=message_logging,
            **kwargs,
        )
        self._required_prefix = required_prefix
        self._normalizer: StringNormalizer = normalizer or (lambda value: value.strip())

    async def async_pre_call_deployment_hook(
        self, kwargs: dict, call_type: Optional["CallTypes"]
    ) -> Optional[dict]:
        updated_kwargs = dict(kwargs)
        updated = False

        if "file_id" in updated_kwargs:
            processed_single, changed = self._process_value(updated_kwargs["file_id"])
            if changed:
                updated_kwargs["file_id"] = processed_single
                updated = True

        if "file_ids" in updated_kwargs:
            processed_many, changed = self._process_value(updated_kwargs["file_ids"])
            if changed:
                updated_kwargs["file_ids"] = processed_many
                updated = True

        return updated_kwargs if updated else kwargs

    def _apply_rules(self, value: str) -> str:
        normalized = self._normalizer(value)
        if self._required_prefix and not normalized.startswith(self._required_prefix):
            normalized = f"{self._required_prefix}{normalized}"
        return normalized

    def _process_value(
        self, value: Union[str, Iterable[str]]
    ) -> tuple[Union[str, Iterable[str]], bool]:
        if isinstance(value, str):
            processed = self._apply_rules(value)
            return processed, processed != value
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            return self._process_iterable(value)
        return value, False

    def _process_iterable(
        self, values: Iterable[str]
    ) -> tuple[list[str], bool]:
        processed_values = []
        changed = False
        for item in values:
            if isinstance(item, str):
                processed = self._apply_rules(item)
                if processed != item:
                    changed = True
                processed_values.append(processed)
            else:
                processed_values.append(item)
        return processed_values, changed
