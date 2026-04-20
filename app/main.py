"""
入口：初始化 LLM 并启动 Agent。

工具无需在此手动注册；
`import tools` 会自动扫描 tools/ 目录下的所有模块，
由各模块内的 @tool 装饰器完成全局注册。

Prompt 模板从 config.yaml + prompts/system.md 分离配置。
"""

from client import HelloAgentsLLM
from agent import ReActAgent

import tools  # noqa: F401 —— 触发 tools/ 目录自动扫描


def main():
    print("🚀 ReAct Agent Demo 启动")
    llm = HelloAgentsLLM()
    agent = ReActAgent(llm=llm)

    question = "编辑app/workspace/test.txt，把小诗的后半部分改为豪放派文风"
    agent.run(question)


if __name__ == "__main__":
    main()