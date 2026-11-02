"""解析器单元测试：全部用临时文件构造样例，不依赖网络。

测试思路（三正两反）：
  正常路径：PDF 有页有文 / DOCX 伪页数量正确 / MD 内容完整
  异常路径：不支持的格式 / 扫描件（空文本 PDF）
"""
import docx as docx_lib
import fitz
import pytest

from app.ingestion.parsers import ParseError, parse_document


# ---------- 测试用的文件工厂 ----------

def _make_pdf(tmp_path, page_texts):
    """生成测试 PDF。注意 fontname="china-s" 是 PyMuPDF 内置中文字体，
    不用它写中文会变成乱码——这也是个真实踩坑点。"""
    path = tmp_path / "sample.pdf"
    with fitz.open() as pdf:
        for text in page_texts:
            page = pdf.new_page()
            if text:
                page.insert_text((72, 72), text, fontname="china-s", fontsize=14)
        pdf.save(path)
    return path


def _make_docx(tmp_path, paragraphs):
    path = tmp_path / "sample.docx"
    doc = docx_lib.Document()
    for para in paragraphs:
        doc.add_paragraph(para)
    doc.save(path)
    return path


# ---------- 正常路径 ----------

def test_pdf_pages_and_text(tmp_path):
    path = _make_pdf(tmp_path, ["年假制度第一页", "年假制度第二页"])
    doc = parse_document(path)
    assert len(doc.pages) == 2
    assert doc.pages[0].page_no == 1
    assert doc.pages[1].page_no == 2
    assert "年假" in doc.pages[0].text


def test_docx_pseudo_pages(tmp_path):
    # 65 段，每 30 段一页 → 应该是 30 + 30 + 5 = 3 个伪页
    path = _make_docx(tmp_path, [f"第{i}段内容" for i in range(65)])
    doc = parse_document(path)
    assert len(doc.pages) == 3
    assert "第1段内容" in doc.pages[0].text


def test_markdown(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text("# 薪酬制度\n\n正文内容第一行", encoding="utf-8")
    doc = parse_document(path)
    assert doc.pages[0].page_no == 1
    assert "正文内容" in doc.full_text


# ---------- 异常路径 ----------

def test_unsupported_format(tmp_path):
    path = tmp_path / "evil.exe"
    path.write_bytes(b"\x00")
    with pytest.raises(ParseError, match="不支持的格式"):
        parse_document(path)


def test_scanned_pdf_raises(tmp_path):
    # 只建页不写字 → 模拟扫描件（有图像无文本层）
    path = _make_pdf(tmp_path, ["", ""])
    with pytest.raises(ParseError, match="扫描"):
        parse_document(path)
