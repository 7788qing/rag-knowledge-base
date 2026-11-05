"""Embedding 层：把文字变成向量（一串数字）。

为什么需要它：
  电脑不懂文字，只懂数字。Embedding 模型把一段文字压成一个向量，
  意思越相近的文字，向量挨得越近——「检索」的本质就是找最近的向量。

三种实现，接口完全一样（可插拔设计，面试可讲）：
  1. OpenAICompatEmbedder：调任意「OpenAI 兼容」的向量服务（默认硅基流动 bge-m3，免费）
  2. FakeEmbedder：测试专用，按文本哈希生成假向量，不联网、不花钱
  3. 本地 BGE（sentence-transformers）：留了位置，以后有显卡/带宽再启用
"""
from __future__ import annotations

import hashlib
from typing import Protocol

from app.config import settings


class Embedder(Protocol):
    """所有 embedding 实现都要遵守的接口约定（Protocol = 只认形状不认血统）。"""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """一批文本 → 一批向量（入库时用）。"""
        ...

    def embed_query(self, text: str) -> list[float]:
        """一句查询 → 一个向量（检索时用）。"""
        ...


class FakeEmbedder:
    """测试专用：不联网，按文本哈希生成固定向量。

    相同文字 → 完全相同的向量。测试里把查询文本设成和某个 chunk
    一模一样，就能稳定测出「最近的向量排第一」，不依赖任何模型。
    """

    def __init__(self, dim: int = 16) -> None:
        self.dim = dim  # 向量维度（每个向量有几个数字）

    def _one(self, text: str) -> list[float]:
        # sha256 把任意文字压成固定长度的字节串，再归一化成 0~1 的小数
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [digest[i % len(digest)] / 255.0 for i in range(self.dim)]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._one(text)


class OpenAICompatEmbedder:
    """生产实现：调任意兼容 OpenAI 格式的向量服务。

    默认用硅基流动的 BAAI/bge-m3（免费、中文好、1024 维）。
    想换别家？只改 .env 里的 EMBEDDING_BASE_URL / EMBEDDING_MODEL，代码不动。

    为什么不在本地跑 BGE：
      本地跑要 torch（约 2GB）+ 模型权重（几百 MB~1GB），CPU 编码也慢；
      API 免费、快、零安装。接口已留好，将来切本地只加一个类。
    """

    BATCH_SIZE = 10  # 一次最多送 10 条，超了分批（各家上限不同，10 是安全值）

    def __init__(self) -> None:
        # 延迟导入：没装 openai 包时，其他代码和测试照常能跑
        from openai import OpenAI

        self._client = OpenAI(
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url,
        )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(model=settings.embedding_model, input=texts)
        data = sorted(resp.data, key=lambda d: d.index)  # 按 index 排回原顺序
        return [d.embedding for d in data]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.BATCH_SIZE):  # 每 10 条切一批
            out.extend(self._embed(texts[i : i + self.BATCH_SIZE]))
        return out

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]


def build_embedder(provider: str | None = None) -> Embedder:
    """小工厂：按配置返回对应的 embedding 实现，上层代码不用关心细节。"""
    provider = provider or settings.embedding_provider
    if provider in ("openai_compat", "dashscope"):
        return OpenAICompatEmbedder()
    if provider == "fake":
        return FakeEmbedder()
    raise ValueError(f"未知的 embedding provider: {provider}")
