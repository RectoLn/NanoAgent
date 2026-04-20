import os
from typing import List, Dict, Any, Generator, Optional

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


class HelloAgentsLLM:
    """
    统一封装的 LLM 客户端：
    - 支持多个 provider（deepseek, kilo 等）
    - 提供 one_chat（单次对话）与 think（流式输出）两种接口
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        # 支持显式传入参数，否则从环境变量读取
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
                "Content-Type": "application/json"
            }
        )

    def one_chat(self, messages: List[Dict], tools: List[Dict] = None, max_tokens: int = 4096) -> Any:
        """单次（非流式）对话接口。"""
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,  # Agent 需要低随机性保证逻辑稳定
            "max_tokens": max_tokens,
        }
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"

        try:
            response = self.client.chat.completions.create(**params)
            return response.choices[0].message
        except Exception as e:
            print(f"❌ LLM 调用失败: {e}")
            return None

    def think(
        self,
        messages: List[Dict],
        stop: Optional[List[str]] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        流式思考接口：以生成器方式逐 token 吐出模型输出 + 结束原因。

        参数:
            messages: OpenAI 格式的消息列表
            stop:     停止序列（ReAct 中常用 ["Observation:"]）
            temperature: 采样温度
            max_tokens: 输出 token 上限（避免网关默认 256 截断）

        返回: 字典生成器
            {"type": "content", "content": str}  # 正常 token
            {"type": "finish", "reason": str}   # 结束原因: stop/length/content_filter/...
        """
        # deepseek-reasoner 不支持 stop/temperature 参数
        is_reasoner = "reasoner" in (self.model or "").lower()

        params = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if not is_reasoner:
            params["temperature"] = temperature
            if stop:
                params["stop"] = stop

        try:
            stream = self.client.chat.completions.create(**params)
            saw_tool_calls = False
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                # deepseek-reasoner 会先输出 reasoning_content（思考过程），再输出 content（最终答案）
                # 思考过程不参与 ReAct 解析，仅做日志
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    pass
                content = getattr(delta, "content", None)
                if content:
                    yield {"type": "content", "content": content}

                # 检测网关错误地返回 function calling 协议
                tool_calls = getattr(delta, "tool_calls", None)
                if tool_calls:
                    saw_tool_calls = True

                # 检查 finish_reason（最后一个 chunk 会带）
                finish_reason = getattr(chunk.choices[0], "finish_reason", None)
                if finish_reason:
                    # 若网关返回 tool_calls 但我们未传 tools，统一归类为 tool_calls
                    if saw_tool_calls and finish_reason != "length":
                        finish_reason = "tool_calls"
                    yield {"type": "finish", "reason": finish_reason}
                    break
        except Exception as e:
            print(f"\n❌ LLM 流式调用失败: {e}")
            yield {"type": "finish", "reason": "error"}
