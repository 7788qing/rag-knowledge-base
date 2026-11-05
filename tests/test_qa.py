"""问答管线测试：用 FakeEmbedder + FakeChat，不联网、不要 API key。"""
import pytest

from app.ingestion.chunker import Chunk
from app.rag.embedder import FakeEmbedder
from app.rag.llm import FakeChat
from app.rag.prompt import build_messages
from app.rag.qa import NO_ANSWER_HINT, QAPipeline, parse_citations
from app.rag.vector_store import VectorStore


@pytest.fixture()
def parts(tmp_path):
    """造一个装了 3 条资料的库，返回 (store, embedder, texts)。"""
    texts = ["年假每年 5 天", "迟到 30 分钟以上按事假半天处理", "工资每月 10 日发放"]
    store = VectorStore(persist_dir=tmp_path)
    chunks = [
        Chunk(text=t, raw_text=t, doc_name="员工手册.md", page_no=i + 1, chunk_index=i)
        for i, t in enumerate(texts)
    ]
    embedder = FakeEmbedder()
    store.add_chunks(chunks, embedder.embed_documents(texts))
    return store, embedder


def test_prompt_numbers_every_source():
    hits = [
        {"doc_name": "a.md", "page_no": 1, "text": "内容A"},
        {"doc_name": "b.md", "page_no": 2, "text": "内容B"},
    ]
    messages = build_messages("怎么请假？", hits)
    user = messages[1]["content"]

    assert "[1] 来源：a.md 第1页" in user
    assert "[2] 来源：b.md 第2页" in user
    assert "内容A" in user and "内容B" in user
    assert "怎么请假？" in user


def test_parse_citations_dedup_and_order():
    hits = [{"doc_name": "a.md", "page_no": 1}, {"doc_name": "b.md", "page_no": 2}]
    cites = parse_citations("结论一[2]，结论二[1][2]。", hits)

    assert [c.index for c in cites] == [2, 1]   # 按首次出现排序，且去重
    assert cites[0].doc_name == "b.md" and cites[0].page_no == 2


def test_parse_citations_ignores_out_of_range():
    hits = [{"doc_name": "a.md", "page_no": 1}]
    cites = parse_citations("乱标一个[9]，再标[1]。", hits)

    assert [c.index for c in cites] == [1]      # [9] 越界被忽略


def test_pipeline_returns_answer_with_citations(parts):
    store, embedder = parts
    llm = FakeChat("迟到超过 30 分钟按事假半天处理[1]。")
    pipeline = QAPipeline(store, embedder, llm)

    result = pipeline.ask("迟到怎么算？", top_k=3)

    assert "事假" in result.answer
    assert len(result.citations) == 1
    assert result.citations[0].doc_name == "员工手册.md"
    assert llm.last_messages is not None                 # 模型确实收到了 prompt
    assert "【资料】" in llm.last_messages[1]["content"]


def test_pipeline_empty_store_returns_hint(tmp_path):
    store = VectorStore(persist_dir=tmp_path)            # 空库
    pipeline = QAPipeline(store, FakeEmbedder(), FakeChat("我不该被调用"))

    result = pipeline.ask("库是空的会怎样？")

    assert result.answer == NO_ANSWER_HINT
    assert result.citations == []
