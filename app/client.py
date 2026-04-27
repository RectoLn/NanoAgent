import os
from typing import List, Dict, Any, Generator, Optional

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


class HelloAgentsLLM:
    """
    统一封装的 LLM 客户端（Tool Call 模式）：
    - 支持多个 provider（deepseek, kilo 等）
    - call(): 非流式，返回完整 choice（含 finish_reason + message + tool_calls）
    - think_stream(): 流式输出 content token（最终答案阶段）
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.base_url = base_url or os.getenv("LLM_BASE_URL")
        self.model = model or os.getenv("LLM_MODEL_ID")

        if not all([self.model, self.api_key, self.base_url]):
            raise ValueError(
                "⚠️ 请检查 .env 文件，确保 LLM_MODEL_ID / LLM_BASE_URL / LLM_API_KEY 均已配置。"
            )

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            default_headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

    def call(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> Optional[Dict[str, Any]]:
        """
        非流式调用（Tool Call 主循环使用）。
        返回字典：{"choice": response.choices[0], "usage": response.usage}
        """
        params: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            params["tools"] = tools
            params["tool_choice"] = tool_choice

        try:
            response = self.client.chat.completions.create(**params)
            return {
                "choice": response.choices[0],
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                } if response.usage else {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            }
        except Exception as e:
            print(f"❌ LLM 调用失败: {e}")
            return None

    def think_stream(
        self,
        messages: List[Dict],
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        流式输出接口（用于最终答案流式展示，不带 tools）。
        产出事件：
            {"type": "content", "content": str}
            {"type": "finish",  "reason":  str}
        """
        is_reasoner = "reasoner" in (self.model or "").lower()
        params: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if not is_reasoner:
            params["temperature"] = temperature

        try:
            stream = self.client.chat.completions.create(**params)
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    yield {"type": "content", "content": content}
                finish_reason = getattr(chunk.choices[0], "finish_reason", None)
                if finish_reason:
                    yield {"type": "finish", "reason": finish_reason}
                    break
        except Exception as e:
            print(f"\n❌ LLM 流式调用失败: {e}")
            yield {"type": "finish", "reason": "error"}
