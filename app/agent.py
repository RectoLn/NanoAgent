import os
import re
import yaml
from pathlib import Path
from typing import Optional, Generator, Dict, Any

from client import HelloAgentsLLM
import registry
from todo_manager import TODO


def _load_config() -> dict:
    """加载 config.yaml"""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_prompt(file_path: str) -> str:
    """读取 Prompt 模板文件"""
    full_path = Path(__file__).parent / file_path
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read().strip()


class ReActAgent:
    """ReAct Agent：Thought / Action / Observation 循环"""

    # Action: 单行；Action Input: 可能跨多行，以 <END_OF_ACTION> 或其他关键字为边界
    ACTION_RE = re.compile(
        r"Action:\s*(?P<action>[^\n]+)\s*\n+"
        r"Action Input:\s*(?P<input>.*?)"
        r"(?=\s*<END_OF_ACTION>|\n\s*(?:Observation:|Action:|Thought:|Final Answer:)|\Z)",
        re.DOTALL,
    )
    FINAL_RE = re.compile(r"Final Answer:\s*(.*?)(?:\n\s*(?:Thought:|Action:|Question:)|\Z)", re.DOTALL)

    def __init__(self, llm: HelloAgentsLLM, config_path: str = None):
        self.llm = llm
        self.config = _load_config()

        agent_cfg = self.config.get("agent", {})
        self.max_steps = agent_cfg.get("max_steps", 10)
        self.temperature = agent_cfg.get("temperature", 0.1)
        # nag 阈值：连续 N 轮未更新 todo 则注入 reminder
        self.nag_threshold = agent_cfg.get("nag_threshold", 3)

        llm_cfg = self.config.get("llm", {})
        self.stop_sequences = llm_cfg.get("stop_sequences", ["Observation:"])

        prompts_cfg = self.config.get("prompts", {})
        prompt_file = prompts_cfg.get("system", "prompts/system.md")
        self.prompt_template = _load_prompt(prompt_file)

        # rounds_since_todo：自上次调用 todo 工具以来经过的轮数
        self._rounds_since_todo = 0

    def _build_prompt(self, question: str) -> str:
        """
        渲染 Prompt 模板。
        使用 str.replace 而非 str.format，避免模板里的 JSON 示例
        （含 `{...}`）被 format 误当作占位符。
        """
        tool_names = ", ".join(registry.get_tool_names())
        tool_descriptions = registry.get_tool_descriptions()
        return (
            self.prompt_template
            .replace("{tool_descriptions}", tool_descriptions)
            .replace("{tool_names}", tool_names)
            .replace("{question}", question)
        )

    def _stream_think(self, prompt: str) -> str:
        """（保留以兼容）聚合 _iter_think 产出为完整字符串并同步打印。"""
        buffer = ""
        for token in self._iter_think(prompt):
            print(token, end="", flush=True)
            buffer += token
        return buffer

    @staticmethod
    def _parse_action(text: str) -> Optional[tuple]:
        match = ReActAgent.ACTION_RE.search(text)
        if not match:
            return None
        action = match.group("action").strip()
        action_input = match.group("input").strip()

        # 清理尾部可能混入的模型续写内容（Thought/Action/Observation/END_OF_ACTION 残留）
        cutoff_patterns = [
            "<END_OF_ACTION",
            "</END_OF_ACTION",
            "\nThought:",
            "\nAction:",
            "\nObservation:",
            "\nFinal Answer:",
        ]
        for pat in cutoff_patterns:
            idx = action_input.find(pat)
            if idx != -1:
                action_input = action_input[:idx]
        action_input = action_input.strip()

        # 如果是 JSON 数组/对象，截取到匹配的闭合括号为止（防止后续垃圾）
        action_input = ReActAgent._trim_balanced_json(action_input)

        # 只去除包裹整个字符串的引号（不影响内部内容）
        if len(action_input) >= 2:
            if (action_input[0] == action_input[-1]) and action_input[0] in ('"', "'"):
                action_input = action_input[1:-1]
        return action, action_input

    @staticmethod
    def _trim_balanced_json(s: str) -> str:
        """若 s 以 [ 或 { 开头，截取到第一个匹配的闭合括号为止。否则原样返回。"""
        s = s.strip()
        if not s or s[0] not in "[{":
            return s
        open_ch = s[0]
        close_ch = "]" if open_ch == "[" else "}"
        depth = 0
        in_str = False
        escape = False
        for i, ch in enumerate(s):
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return s[: i + 1]
        return s  # 括号不匹配就原样返回，后续 json.loads 报错时提示模型

    @staticmethod
    def _parse_final(text: str) -> Optional[str]:
        match = ReActAgent.FINAL_RE.search(text)
        if not match:
            return None
        return match.group(1).strip()

    def _maybe_nag(self) -> Optional[str]:
        """
        连续 nag_threshold 轮未调用 todo 工具时，
        返回一段 <reminder> 文本注入到下一轮 Prompt；
        否则返回 None。
        """
        if self._rounds_since_todo < self.nag_threshold:
            return None
        summary = TODO.summary()
        return (
            "<reminder>\n"
            f"你已连续 {self._rounds_since_todo} 轮未更新 todo 列表。{summary}\n"
            "请立即调用 todo 工具刷新任务进度（标记已完成项、更新 in_progress）。\n"
            "</reminder>"
        )

    def run_iter(self, question: str) -> Generator[Dict[str, Any], None, None]:
        """
        以生成器方式执行 ReAct 循环，逐步产出事件字典。
        事件类型：
          - {"type": "question", "content": str}
          - {"type": "step_start", "step": int}
          - {"type": "reminder", "content": str}
          - {"type": "thought_chunk", "content": str}  # 流式 token
          - {"type": "action", "name": str, "input": str}
          - {"type": "observation", "content": str}
          - {"type": "final", "content": str}
          - {"type": "error", "content": str}
          - {"type": "done"}
        """
        yield {"type": "question", "content": question}
        prompt = self._build_prompt(question)
        self._rounds_since_todo = 0

        for step in range(1, self.max_steps + 1):
            yield {"type": "step_start", "step": step}

            nag = self._maybe_nag()
            if nag:
                yield {"type": "reminder", "content": nag}
                prompt += f"\n{nag}\n"

            # 流式收集本轮输出，逐 token 产出
            output = ""
            think_result = None
            gen = self._iter_think(prompt)
            while True:
                try:
                    token = next(gen)
                    output += token
                    yield {"type": "thought_chunk", "content": token}
                except StopIteration as e:
                    think_result = e.value
                    break

            finish_reason = think_result.finish_reason if think_result else "stop"
            print(f"\n[DEBUG step={step}] finish_reason={finish_reason}, output_len={len(output)}")
            print(f"[DEBUG output tail]: ...{repr(output[-200:])}")

            # 检查 Final Answer
            final = self._parse_final(output)
            if final:
                yield {"type": "final", "content": final}
                yield {"type": "done"}
                return

            # 检查是否因长度截断
            if finish_reason == "length":
                yield {"type": "error", "content": "模型输出因长度限制被截断，请简化问题或增加 max_tokens"}
                yield {"type": "done"}
                return

            # 空输出 / tool_calls 路径 → 注入纠正提示重试一次
            if finish_reason == "tool_calls" or len(output.strip()) == 0:
                correction = (
                    "\n<system>\n"
                    "你刚才尝试使用 function calling / tool_calls 协议或输出为空。\n"
                    "本系统只接受纯文本 ReAct 格式：\n"
                    "Thought: ...\nAction: <tool_name>\nAction Input: <input>\n<END_OF_ACTION>\n"
                    "请立即按此格式重新输出。\n"
                    "</system>\n"
                )
                prompt += correction
                continue

            # 解析 Action
            parsed = self._parse_action(output)
            if not parsed:
                yield {"type": "error", "content": "未能解析到 Action，提前终止"}
                yield {"type": "done"}
                return

            action, action_input = parsed
            if action_input.lower() in {"none", "null", ""}:
                action_input = ""

            yield {"type": "action", "name": action, "input": action_input}

            observation = registry.execute(action, action_input)
            yield {"type": "observation", "content": observation}

            if action == "todo":
                self._rounds_since_todo = 0
                # 推送最新的 todo 快照给前端
                yield {"type": "todo_update", "items": list(TODO.items)}
            else:
                self._rounds_since_todo += 1

            prompt += output
            if not prompt.endswith("\n"):
                prompt += "\n"
            prompt += f"Observation: {observation}\n"

        yield {"type": "error", "content": f"已达到 max_steps={self.max_steps} 上限"}
        yield {"type": "done"}

    class _ThinkResult:
        def __init__(self):
            self.finish_reason = "stop"

    def _iter_think(self, prompt: str) -> Generator[str, None, _ThinkResult]:
        """
        流式调用 LLM，产出 token；客户端侧 stop 截断。
        返回: _ThinkResult 对象，包含 finish_reason
        """
        messages = [{"role": "user", "content": prompt}]
        buffer = ""
        result = self._ThinkResult()

        for event in self.llm.think(
            messages=messages,
            stop=self.stop_sequences,
            temperature=self.temperature,
        ):
            if event["type"] == "content":
                token = event["content"]
                combined = buffer + token
                hit_idx = -1
                for s in self.stop_sequences:
                    idx = combined.find(s)
                    if idx != -1 and (hit_idx == -1 or idx < hit_idx):
                        hit_idx = idx
                if hit_idx != -1:
                    truncated = combined[:hit_idx]
                    delta = truncated[len(buffer):]
                    if delta:
                        yield delta
                    result.finish_reason = "stop"
                    break
                yield token
                buffer = combined
            elif event["type"] == "finish":
                result.finish_reason = event["reason"]
                break

        return result

    def run(self, question: str) -> str:
        """
        阻塞式执行：消费 run_iter 并聚合最终答案。
        保留对 CLI 的兼容，同时打印中间事件便于调试。
        """
        final_text = ""
        for event in self.run_iter(question):
            t = event["type"]
            if t == "question":
                print(f"\n🤔 用户问题: {event['content']}\n")
            elif t == "step_start":
                print(f"\n--- 第 {event['step']} 步 ---")
            elif t == "reminder":
                print(f"\n⏰ 注入 reminder:\n{event['content']}\n")
            elif t == "thought_chunk":
                print(event["content"], end="", flush=True)
            elif t == "action":
                print(f"\n[Action] {event['name']}  [Input] {event['input'][:80]}")
            elif t == "observation":
                print(f"Observation: {event['content']}")
            elif t == "final":
                final_text = event["content"]
                print(f"\n✅ 最终答案: {final_text}")
            elif t == "error":
                print(f"\n⚠️ {event['content']}")
                if not final_text:
                    final_text = f"（{event['content']}）"
        return final_text