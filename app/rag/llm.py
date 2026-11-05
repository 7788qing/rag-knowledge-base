"""LLM 层：把「messages 列表」变成「一段回答」。

为什么单独一层：
  1. 换模型只改这里（DeepSeek / 通义 / OpenAI / Ollama 都用 OpenAI 兼容格式）；
  2. 测试时塞一个假客户端（FakeChat），不联网、不花钱、秒跑。
"""
from __future__ import annotations

from typing import Protocol

from app.config import settings


class ChatClient(Protocol):
    """接口约定：会「吃 messages、吐字符串」就算一个聊天客户端。"""

    def chat(self, messages: list[dict]) -> str: ...


class OpenAICompatChat:
    """生产实现：调任意兼容 OpenAI 格式的对话模型（默认 DeepSeek）。

    temperature=0.1：问答场景要的是「照资料说」，不是「自由发挥」。
    值越高越有创造性，也越容易偏离资料。
    """

    def __init__(self, model: str | None = None) -> None:
        from openai import OpenAI  # 延迟导入：不装 openai 也能跑测试

        self._client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
        self.model = model or settings.llm_model

    def chat(self, messages: list[dict]) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1,
        )
        return resp.choices[0].message.content or ""


class FakeChat:
    """测试专用：不管问什么都返回预设答案，并记下收到的 messages。

    last_messages 的用途：测试可以断言「资料确实被塞进 prompt 了」。
    """

    def __init__(self, reply: str = "根据资料，答案是 42[1]。") -> None:
        self.reply = reply
        self.last_messages: list[dict] | None = None

    def chat(self, messages: list[dict]) -> str:
        self.last_messages = messages
        return self.reply
