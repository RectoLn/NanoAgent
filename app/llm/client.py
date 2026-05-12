import openai
from typing import Optional, Iterator

from .provider_config import resolve
from .types import LLMResponse, ToolCall, Usage, StreamEvent


class LLMClient:
    def __init__(
        self,
        purpose: str = "chat",
        override: Optional[dict] = None,
    ):
        cfg = resolve(purpose, override)
        self.provider = cfg.provider
        self.base_url = cfg.base_url
        self.model = cfg.model
        self._model = cfg.model
        self._is_reasoner = "reasoner" in cfg.model.lower()
        self._client = openai.OpenAI(
            api_key=cfg.api_key or "local",
            base_url=cfg.base_url,
        )

    def call(
        self,
        messages: list,
        tools: Optional[list] = None,
        tool_choice: str = "auto",
        temperature: float = 0.1,
        max_tokens: int = 16384,
    ) -> LLMResponse:
        params = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if not self._is_reasoner:
            params["temperature"] = temperature
        if tools:
            params["tools"] = tools
            params["tool_choice"] = tool_choice
        resp = self._client.chat.completions.create(**params)
        choice = resp.choices[0]
        tcs = []
        if choice.message.tool_calls:
            tcs = [
                ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments)
                for tc in choice.message.tool_calls
            ]
        usage = None
        if resp.usage:
            usage = Usage(
                prompt_tokens=resp.usage.prompt_tokens,
                completion_tokens=resp.usage.completion_tokens,
                total_tokens=resp.usage.total_tokens,
            )
        return LLMResponse(
            content=choice.message.content,
            tool_calls=tcs,
            finish_reason=choice.finish_reason,
            usage=usage,
        )

    def stream(
        self,
        messages: list,
        temperature: float = 0.1,
        max_tokens: int = 16384,
    ) -> Iterator[StreamEvent]:
        params = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if not self._is_reasoner:
            params["temperature"] = temperature
        for chunk in self._client.chat.completions.create(**params):
            delta = chunk.choices[0].delta
            if getattr(delta, "reasoning_content", None):
                yield {"type": "reason", "content": delta.reasoning_content}
            elif delta.content:
                yield {"type": "content", "content": delta.content}
        yield {"type": "finish", "content": ""}
