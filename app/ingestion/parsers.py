"""文档解析器：把不同格式的文档统一解析成「带页码的 Page 列表」。

为什么要统一成 Page 这个中间结构（本模块的核心设计）：
  1. 引用溯源需要「这段话出自第几页」——答案末尾的 [1](员工手册.pdf, 第12页) 靠它实现；
  2. 分块、入库等上层代码只面对一种数据结构，彻底不关心原始格式；
  3. 新增格式（如 PPT、HTML）只需加一个解析函数，上层零改动 —— 开闭原则。

页码语义：
  - PDF：真实物理页码；
  - DOCX：每 30 个段落合成一个「伪页」，引用显示为逻辑段落块；
  - MD/TXT：每 80 行一个伪页。
"""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Page:
    text: str
    page_no: int  # 从 1 开始，供引用溯源


@dataclass
class ParsedDoc:
    doc_name: str
    pages: list[Page] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """整篇拼接文本，调试时看全貌用。"""
        return "\n".join(p.text for p in self.pages)


class ParseError(Exception):
    """解析失败：格式不支持、文件不存在、或扫描件无文本层。"""


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".md", ".txt"}

# 伪页大小（Word 按段落、MD/TXT 按行数切）
_PSEUDO_PAGE_PARAGRAPHS = 30
_PSEUDO_PAGE_LINES = 80


def parse_document(path: str | Path) -> ParsedDoc:
    """解析入口：先做校验，再按后缀路由给具体的解析器。

    这是典型的「简单工厂 + 策略模式」：本函数是唯一对外的门（Facade），
    外界永远不需要知道内部有几种解析器。
    """
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix not in SUPPORTED_EXTENSIONS:
        raise ParseError(f"不支持的格式 {suffix or '(无后缀)'}，当前支持 {sorted(SUPPORTED_EXTENSIONS)}")
    if not path.exists():
        raise ParseError(f"文件不存在: {path}")

    parser = {
        ".pdf": _parse_pdf,
        ".docx": _parse_docx,
        ".md": _parse_text_like,
        ".txt": _parse_text_like,
    }[suffix]
    doc = parser(path)

    # 扫描件保护：PDF 扫描件每页都有坐标图形，但 get_text 返回空字符串。
    # 提前拦截，避免后面入库一堆空 chunk。
    if not any(p.text.strip() for p in doc.pages):
        raise ParseError("未解析到任何文本，疑似扫描版 PDF（OCR 支持将在阶段3提供）")
    return doc


def _parse_pdf(path: Path) -> ParsedDoc:
    """PyMuPDF 逐页提取。get_text("text") 按阅读顺序返回纯文本。"""
    import fitz  # PyMuPDF 的导入名，装的是 pymupdf 这个包

    pages: list[Page] = []
    with fitz.open(path) as pdf:
        for i, page in enumerate(pdf, start=1):
            pages.append(Page(text=page.get_text("text"), page_no=i))
    return ParsedDoc(doc_name=path.name, pages=pages)


def _parse_docx(path: Path) -> ParsedDoc:
    """python-docx 提取段落。Word 没有页码概念（分页是渲染时才决定的），
    所以每 30 个非空段落合成一个伪页，让引用至少能定位到逻辑块。"""
    import docx as docx_lib

    document = docx_lib.Document(path)
    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]

    pages, buf = [], []
    for para in paragraphs:
        buf.append(para)
        if len(buf) >= _PSEUDO_PAGE_PARAGRAPHS:
            pages.append(Page(text="\n".join(buf), page_no=len(pages) + 1))
            buf = []
    if buf:  # 别忘了最后不满 30 段的尾巴
        pages.append(Page(text="\n".join(buf), page_no=len(pages) + 1))
    return ParsedDoc(doc_name=path.name, pages=pages)


def _parse_text_like(path: Path) -> ParsedDoc:
    """Markdown / TXT：直接读 UTF-8 文本，每 80 行一个伪页。"""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    pages = [
        Page(
            text="\n".join(lines[i : i + _PSEUDO_PAGE_LINES]),
            page_no=i // _PSEUDO_PAGE_LINES + 1,
        )
        for i in range(0, len(lines), _PSEUDO_PAGE_LINES)
    ]
    return ParsedDoc(doc_name=path.name, pages=pages)
