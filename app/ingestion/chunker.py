"""文本分块器：把「页」切成适合向量化的「块」（chunk）。

为什么必须分块，不能整篇直接向量化：
  1. Embedding 模型有输入上限（BGE-Large 约 512 token），整篇塞不进去；
  2. 即使塞得进去，一整篇压成一个向量，语义会被"平均"掉，检索精度骤降；
  3. 引用溯源要求定位到具体的段落，块是检索与引用的最小单位。

三个关键设计：
  1. 递归分割（RecursiveCharacterTextSplitter）：优先按"段落 → 换行 → 句号 → 逗号"
     逐级降级切分，尽量在语义边界处断开，而不是按固定字数硬切。
  2. 重叠窗口（overlap）：相邻块共享 80 字左右，避免一句话被拦腰截断后两边都读不通。
  3. 上下文前缀（context_prefix）：Markdown 的标题路径（如「员工手册 > 考勤制度」）
     注入到块正文前面，让块脱离原文后仍然知道自己属于哪个章节——这对检索命中率
     提升很明显，也是简历上可以讲的一个细节。
"""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings
from app.ingestion.parsers import ParsedDoc, parse_document

# 中文文本的分隔符优先级：从"最像语义边界"到"最不像"，由 splitter 逐级降级尝试。
# 注意顺序不能乱：空字符串 "" 必须放最后，它代表"实在切不开就按字符硬切"。
SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]

# 前缀把预算吃掉后，正文至少还要留这么多字，否则块会碎成没有信息量的渣
_MIN_BODY_BUDGET = 50


@dataclass
class Chunk:
    """检索与入库的最小单元。"""
    text: str                    # 最终文本（含上下文前缀），送去算向量
    raw_text: str                # 原始片段（不含前缀），调试和展示用
    doc_name: str                # 来源文件名
    page_no: int                 # 来源页码，供引用溯源
    chunk_index: int             # 全文内的全局序号，从 0 开始
    context_prefix: str = ""     # 标题路径，如 "员工手册 > 考勤制度"

    def to_metadata(self) -> dict:
        """转成 Chroma 需要的扁平元数据（只允许 str/int/float/bool）。"""
        return {
            "doc_name": self.doc_name,
            "page_no": self.page_no,
            "chunk_index": self.chunk_index,
            "context_prefix": self.context_prefix,
        }

    @property
    def citation(self) -> str:
        """引用标签，最终答案里的 [1]（员工手册.pdf · 第12页）用得上。"""
        return f"{self.doc_name} · 第{self.page_no}页"


@lru_cache(maxsize=8)
def _make_splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    """按参数缓存 splitter，避免同一份配置被反复构造（小优化，顺手养成习惯）。"""
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=SEPARATORS,
        keep_separator=True,   # 保留句号/换行本身，否则句子尾巴的标点会丢
        length_function=len,   # 中文按字符数计长度（不是 token，够用且零成本）
    )


def _parse_heading(line: str) -> tuple[int, str] | None:
    """识别 Markdown 标题行，返回 (层级, 标题文字)；不是标题返回 None。"""
    stripped = line.lstrip()
    if not stripped.startswith("#"):
        return None
    level = len(stripped) - len(stripped.lstrip("#"))
    title = stripped[level:].strip()
    if not title or level > 6:
        return None
    return level, title


def _split_markdown_segments(text: str, inherited_path: list[str]) -> tuple[list[tuple[list[str], str]], list[str]]:
    """把一页 Markdown 切成 [(标题路径, 正文), ...]，并返回本页结束时的标题路径。

    标题路径要跨页继承：一个章节往往横跨好几页，第二页开头没有 # 标题，
    但它其实仍然属于上一页的章节。
    """
    segments: list[tuple[list[str], str]] = []
    path = list(inherited_path)
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            segments.append((list(path), body))
        buffer.clear()

    for line in text.splitlines():
        heading = _parse_heading(line)
        if heading:
            flush()                       # 遇到新标题，先把上一段正文收尾
            level, title = heading
            path = path[: level - 1] + [title]   # 同级或更浅的标题会覆盖掉旧路径
            continue
        buffer.append(line)
    flush()
    return segments, path


def chunk_pages(
    doc: ParsedDoc,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[Chunk]:
    """主入口：把解析好的文档切成 chunk 列表。

    chunk_size / chunk_overlap 参数默认取 config（可在 .env 里改），
    测试时可以直接传入覆盖默认值。
    """
    size = chunk_size or settings.chunk_size
    overlap = chunk_overlap if chunk_overlap is not None else settings.chunk_overlap
    if overlap >= size:
        raise ValueError(f"chunk_overlap({overlap}) 必须小于 chunk_size({size})，否则会无限重叠")

    is_markdown = doc.doc_name.lower().endswith((".md", ".markdown"))
    chunks: list[Chunk] = []
    heading_path: list[str] = []

    for page in doc.pages:
        if not page.text.strip():     # 空白页直接跳过，不产生空 chunk
            continue

        if is_markdown:
            segments, heading_path = _split_markdown_segments(page.text, heading_path)
        else:
            segments = [([], page.text)]

        for path, body in segments:
            prefix = " > ".join(path)
            # 前缀要占字符预算：总长 = 前缀 + 换行 + 正文，不能只顾正文超长
            budget = max(size - len(prefix) - 1, _MIN_BODY_BUDGET) if prefix else size
            splitter = _make_splitter(budget, min(overlap, budget // 2))

            for piece in splitter.split_text(body):
                piece = piece.strip()
                if not piece:
                    continue
                chunks.append(
                    Chunk(
                        text=f"{prefix}\n{piece}" if prefix else piece,
                        raw_text=piece,
                        doc_name=doc.doc_name,
                        page_no=page.page_no,
                        chunk_index=len(chunks),   # 全局递增，天然唯一
                        context_prefix=prefix,
                    )
                )
    return chunks


def chunk_file(path: str | Path) -> list[Chunk]:
    """便捷入口：解析 + 分块一条龙，步骤 4 入库时直接调它。"""
    return chunk_pages(parse_document(path))
