"""分块器测试：覆盖「切得开、切得准、元数据对」三类行为。"""
import pytest

from app.ingestion.chunker import chunk_pages
from app.ingestion.parsers import Page, ParsedDoc


def _long_text(sentences: int = 80) -> str:
    """造一段长中文，句子之间有句号和换行，模拟真实文档。"""
    return "\n\n".join(
        f"第{i}条：员工应当遵守公司信息安全管理制度，不得擅自外传涉密资料，违者按规定处理。"
        for i in range(sentences)
    )


def test_split_long_text_into_multiple_chunks():
    doc = ParsedDoc(doc_name="员工手册.txt", pages=[Page(text=_long_text(), page_no=1)])

    chunks = chunk_pages(doc, chunk_size=200, chunk_overlap=40)

    assert len(chunks) > 1, "80 句话应该切出多块"
    assert all(len(c.raw_text) <= 200 for c in chunks), "每块正文不能超过 chunk_size"


def test_adjacent_chunks_share_overlap():
    doc = ParsedDoc(doc_name="员工手册.txt", pages=[Page(text=_long_text(), page_no=1)])

    chunks = chunk_pages(doc, chunk_size=200, chunk_overlap=60)

    overlaps = [chunks[i].raw_text[-30:] in chunks[i + 1].raw_text for i in range(len(chunks) - 1)]
    assert any(overlaps), "overlap 应让相邻块共享一段文字，避免句子被拦腰截断"


def test_chunk_index_is_global_and_page_no_kept():
    doc = ParsedDoc(
        doc_name="a.txt",
        pages=[
            Page(text="第一页的内容。" * 60, page_no=1),
            Page(text="第二页的内容。" * 60, page_no=2),
        ],
    )

    chunks = chunk_pages(doc, chunk_size=120, chunk_overlap=20)

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert {c.page_no for c in chunks} == {1, 2}
    assert all(c.doc_name == "a.txt" for c in chunks)


def test_markdown_heading_prefix_injected():
    md = "# 员工手册\n\n## 考勤制度\n\n" + "迟到三次以上扣除当月全勤奖，具体情况详见考勤管理办法。" * 12
    doc = ParsedDoc(doc_name="handbook.md", pages=[Page(text=md, page_no=1)])

    chunks = chunk_pages(doc, chunk_size=150, chunk_overlap=20)

    assert chunks
    first = chunks[0]
    assert first.context_prefix == "员工手册 > 考勤制度"
    assert first.text.startswith("员工手册 > 考勤制度\n")
    assert all(len(c.text) <= 150 for c in chunks), "前缀占用的字符也要算进预算"


def test_heading_path_inherited_across_pages():
    doc = ParsedDoc(
        doc_name="handbook.md",
        pages=[
            Page(text="# 第一章 总则\n\n本章规定公司基本制度。", page_no=1),
            Page(text="第二章的正文直接开始，没有写标题。" * 10, page_no=2),
        ],
    )

    chunks = chunk_pages(doc, chunk_size=100, chunk_overlap=10)

    second_page_chunks = [c for c in chunks if c.page_no == 2]
    assert second_page_chunks
    assert all(c.context_prefix == "第一章 总则" for c in second_page_chunks)


def test_blank_page_skipped():
    doc = ParsedDoc(
        doc_name="x.txt",
        pages=[Page(text="   \n\n  ", page_no=1), Page(text="这一页有内容。", page_no=2)],
    )

    chunks = chunk_pages(doc, chunk_size=100, chunk_overlap=10)

    assert len(chunks) == 1
    assert chunks[0].page_no == 2


def test_overlap_not_less_than_chunk_size_raises():
    doc = ParsedDoc(doc_name="x.txt", pages=[Page(text="内容。", page_no=1)])

    with pytest.raises(ValueError, match="必须小于"):
        chunk_pages(doc, chunk_size=100, chunk_overlap=100)


def test_metadata_is_flat_for_vector_store():
    doc = ParsedDoc(doc_name="staff.md", pages=[Page(text="# 制度\n\n正文内容。", page_no=3)])

    meta = chunk_pages(doc, chunk_size=100, chunk_overlap=10)[0].to_metadata()

    assert meta == {
        "doc_name": "staff.md",
        "page_no": 3,
        "chunk_index": 0,
        "context_prefix": "制度",
    }
    assert all(isinstance(v, (str, int, float, bool)) for v in meta.values())
