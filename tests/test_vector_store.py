"""向量入库测试：全部用 FakeEmbedder，不联网、不要 API key、不要显卡。"""
import pytest

from app.ingestion.chunker import Chunk
from app.rag.embedder import FakeEmbedder
from app.rag.vector_store import VectorStore


def _chunk(i: int, text: str, doc: str = "测试文档.md", page: int = 1) -> Chunk:
    """测试小工具：快速造一个 chunk，省得每次写全 6 个字段。"""
    return Chunk(text=text, raw_text=text, doc_name=doc, page_no=page, chunk_index=i)


def test_add_and_count(tmp_path):
    store = VectorStore(persist_dir=tmp_path)
    chunks = [_chunk(i, f"第{i}块内容") for i in range(3)]
    vectors = FakeEmbedder().embed_documents([c.text for c in chunks])

    assert store.add_chunks(chunks, vectors) == 3
    assert store.count() == 3


def test_search_exact_match_ranks_first(tmp_path):
    store = VectorStore(persist_dir=tmp_path)
    texts = ["如何申请年假", "考勤打卡规定", "薪资发放日期"]
    chunks = [_chunk(i, t) for i, t in enumerate(texts)]
    embedder = FakeEmbedder()
    store.add_chunks(chunks, embedder.embed_documents(texts))

    hits = store.search(embedder.embed_query("如何申请年假"), top_k=3)
    assert hits[0]["text"] == "如何申请年假"   # 完全相同的文字 → 相同向量 → 必排第一
    assert hits[0]["distance"] == pytest.approx(0.0, abs=1e-6)


def test_metadata_roundtrip(tmp_path):
    store = VectorStore(persist_dir=tmp_path)
    chunk = Chunk(
        text="员工手册 > 考勤\n正文内容",
        raw_text="正文内容",
        doc_name="员工手册.md",
        page_no=12,
        chunk_index=5,
        context_prefix="员工手册 > 考勤",
    )
    embedder = FakeEmbedder()
    store.add_chunks([chunk], embedder.embed_documents([chunk.text]))

    hit = store.search(embedder.embed_query(chunk.text), top_k=1)[0]
    assert hit["doc_name"] == "员工手册.md"
    assert hit["page_no"] == 12
    assert hit["chunk_index"] == 5
    assert hit["context_prefix"] == "员工手册 > 考勤"


def test_top_k_limits_results(tmp_path):
    store = VectorStore(persist_dir=tmp_path)
    chunks = [_chunk(i, f"内容{i}") for i in range(5)]
    embedder = FakeEmbedder()
    store.add_chunks(chunks, embedder.embed_documents([c.text for c in chunks]))

    hits = store.search(embedder.embed_query("内容0"), top_k=2)
    assert len(hits) == 2  # 库里有 5 条，但 top_k=2 就只回 2 条


def test_persistence_across_instances(tmp_path):
    store1 = VectorStore(persist_dir=tmp_path)
    chunks = [_chunk(0, "重启之后我还在")]
    store1.add_chunks(chunks, FakeEmbedder().embed_documents([c.text for c in chunks]))

    store2 = VectorStore(persist_dir=tmp_path)  # 新开一个实例，模拟「程序重启」
    assert store2.count() == 1


def test_clear_empties_store(tmp_path):
    store = VectorStore(persist_dir=tmp_path)
    chunks = [_chunk(0, "待清空的内容")]
    store.add_chunks(chunks, FakeEmbedder().embed_documents([c.text for c in chunks]))

    store.clear()
    assert store.count() == 0
