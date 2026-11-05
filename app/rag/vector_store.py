"""向量库层：Chroma 的薄封装。

为什么阶段 1 选 Chroma：
  纯本地、零配置、pip 即装；数据落盘在 data/chroma/，重启不丢。
  以后要上企业级（分布式、亿级向量）再换 Milvus / pgvector，
  本文件对外的三个方法不变——这就是分层的意义。

新手必踩的两个坑，这里提前踩掉：
  1. 必须显式设 cosine（余弦）距离：Chroma 默认用 L2（欧氏距离），
     对文本向量来说 cosine 才是正确的相似度算法。
  2. Chroma 的 metadata 只能存 str/int/float/bool 四种简单类型，
     所以 Chunk.to_metadata() 早早就把对象「翻译」成了字典。
"""
from __future__ import annotations

from pathlib import Path

import chromadb

from app.config import settings
from app.ingestion.chunker import Chunk, chunk_file
from app.rag.embedder import Embedder

_COSINE = {"hnsw:space": "cosine"}  # 显式声明余弦距离，别用默认的 L2


class VectorStore:
    """对 Chroma 的一层薄封装：入库、检索、清空。"""

    def __init__(self, persist_dir: Path | None = None, collection_name: str = "kb_chunks") -> None:
        # PersistentClient = 数据写硬盘（重启不丢）；传 persist_dir 是为了测试隔离
        self.client = chromadb.PersistentClient(path=str(persist_dir or settings.chroma_dir))
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata=_COSINE,
        )

    def add_chunks(self, chunks: list[Chunk], embeddings: list[list[float]]) -> int:
        """把 chunk 连同向量写进库，返回写入条数。

        id 必须唯一：用「文件名#页码#块序号」拼出来，天然不会撞车。
        """
        if not chunks:
            return 0
        ids = [f"{c.doc_name}#{c.page_no}#{c.chunk_index}" for c in chunks]
        documents = [c.text for c in chunks]  # 存带前缀的完整文本，后面拼 prompt 直接用
        metadatas = [c.to_metadata() for c in chunks]
        self.collection.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
        return len(ids)

    def search(self, query_embedding: list[float], top_k: int | None = None) -> list[dict]:
        """按向量找最近的前 top_k 条，返回字典列表（带原文、元数据、距离）。"""
        k = top_k or settings.top_k
        res = self.collection.query(query_embeddings=[query_embedding], n_results=k)

        hits: list[dict] = []
        for i in range(len(res["ids"][0])):  # query 只传了一条，取第 0 组结果
            hits.append(
                {
                    "id": res["ids"][0][i],
                    "text": res["documents"][0][i],
                    "distance": res["distances"][0][i],  # 越小越相似（cosine 距离）
                    **res["metadatas"][0][i],  # doc_name / page_no / ... 直接摊平进来
                }
            )
        return hits

    def count(self) -> int:
        """库里现在有多少条。"""
        return self.collection.count()

    def clear(self) -> None:
        """清空整个 collection（重新入库前用）。"""
        name = self.collection.name
        self.client.delete_collection(name)
        self.collection = self.client.get_or_create_collection(name=name, metadata=_COSINE)


def ingest_file(path: str | Path, embedder: Embedder, store: VectorStore) -> int:
    """一条龙：解析 → 分块 → 向量化 → 入库，返回入库条数。

    步骤 6 的「上传文档」接口直接调这一个函数就够了。
    """
    chunks = chunk_file(path)
    embeddings = embedder.embed_documents([c.text for c in chunks])
    return store.add_chunks(chunks, embeddings)
