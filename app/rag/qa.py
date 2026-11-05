"""问答管线：检索 → 组装 Prompt → 调大模型 → 解析引用。

数据流：
  问题 → 向量化 → Chroma 检索 top_k → 编号拼进 prompt → LLM 回答
  → 正则抓 [n] → 映射回「文档名 + 页码」→ Answer 对象
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from loguru import logger

from app.config import settings
from app.rag.embedder import Embedder
from app.rag.llm import ChatClient
from app.rag.prompt import build_messages
from app.rag.vector_store import VectorStore

_CITE_RE = re.compile(r"\[(\d+)\]")

# 资料不足时的标准回答。用常量而不是散落的字符串，方便测试和改文案。
NO_ANSWER_HINT = "资料中没有相关信息"


@dataclass
class Citation:
    index: int      # 答案里的编号，如 [2]
    doc_name: str
    page_no: int


@dataclass
class Answer:
    question: str
    answer: str
    citations: list[Citation] = field(default_factory=list)
    hits: list[dict] = field(default_factory=list)  # 原始检索结果，调试用


def parse_citations(text: str, hits: list[dict]) -> list[Citation]:
    """从答案里抓 [n]，映射回来源。

    两个防御：
      1. 越界编号（如只给了 3 条资料却标 [9]）直接忽略，防模型乱标；
      2. 同一编号重复出现只算一次，去重后按首次出现顺序返回。
    """
    seen: list[int] = []
    for m in _CITE_RE.findall(text):
        n = int(m)
        if 1 <= n <= len(hits) and n not in seen:
            seen.append(n)
    return [
        Citation(index=n, doc_name=hits[n - 1]["doc_name"], page_no=hits[n - 1]["page_no"])
        for n in seen
    ]


class QAPipeline:
    """把三件工具（向量库、向量化、大模型）串成一条问答流水线。

    构造时注入依赖（依赖注入）：测试可以换成假实现，
    生产时换成真的，管线代码一行不用改。
    """

    def __init__(self, store: VectorStore, embedder: Embedder, llm: ChatClient) -> None:
        self.store = store
        self.embedder = embedder
        self.llm = llm

    def ask(self, question: str, top_k: int | None = None) -> Answer:
        k = top_k or settings.top_k
        t0 = time.perf_counter()

        query_vec = self.embedder.embed_query(question)
        hits = self.store.search(query_vec, top_k=k)
        t_retrieve = (time.perf_counter() - t0) * 1000

        # 检索为空：不要硬让模型编，直接回固定话术
        if not hits:
            logger.warning("检索为空，返回无资料话术 | question={!r}", question)
            return Answer(question=question, answer=NO_ANSWER_HINT)

        messages = build_messages(question, hits)
        t1 = time.perf_counter()
        raw = self.llm.chat(messages)
        t_llm = (time.perf_counter() - t1) * 1000

        citations = parse_citations(raw, hits)
        logger.info(
            "问答完成 | hits={} retrieve={:.0f}ms llm={:.0f}ms cited={}",
            len(hits),
            t_retrieve,
            t_llm,
            [c.index for c in citations],
        )
        return Answer(question=question, answer=raw, citations=citations, hits=hits)
