"""FastAPI 接口层：把 RAG 能力暴露成 HTTP 接口。

五个接口（Postman / 浏览器都能直接调）：

  GET    /health                 健康检查
  POST   /api/documents          上传文档（解析→分块→向量化→入库）
  GET    /api/documents          文档列表
  DELETE /api/documents/{name}   删除某个文档
  POST   /api/ask                提问，返回答案 + 引用

设计要点：
  1. 所有工具（向量库/向量化/大模型）在 lifespan 里建一次，全进程复用；
  2. 用 Depends 注入：测试时整体替换成假实现，接口代码一行不用改；
  3. 接口只做「翻译」——把 HTTP 请求翻译成函数调用，业务逻辑都在 app/rag 里。
"""
from __future__ import annotations

import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from loguru import logger
from pydantic import BaseModel, Field

from app.config import settings
from app.ingestion.parsers import ParseError
from app.rag.embedder import Embedder, build_embedder
from app.rag.llm import ChatClient, OpenAICompatChat
from app.rag.qa import QAPipeline
from app.rag.vector_store import VectorStore, ingest_file

UPLOAD_DIR = settings.data_dir / "uploads"

ALLOWED_SUFFIX = {".pdf", ".docx", ".md", ".markdown", ".txt"}


# ---------------------------------------------------------------- 单例与注入

_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """服务启动时建一次对象，关闭时释放。"""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    _state["store"] = VectorStore()
    _state["embedder"] = build_embedder()
    _state["llm"] = OpenAICompatChat()
    logger.info("服务启动 | 库内 {} 块 | 模型 {}", _state["store"].count(), settings.llm_model)
    yield
    _state.clear()


def get_store() -> VectorStore:
    return _state["store"]


def get_embedder() -> Embedder:
    return _state["embedder"]


def get_llm() -> ChatClient:
    return _state["llm"]


def get_pipeline(
    store: VectorStore = Depends(get_store),
    embedder: Embedder = Depends(get_embedder),
    llm: ChatClient = Depends(get_llm),
) -> QAPipeline:
    """每次请求临时组装一条管线，三个零件都是共享的。"""
    return QAPipeline(store, embedder, llm)


app = FastAPI(title="私有知识库 RAG 问答", version="0.6.0", lifespan=lifespan)


# ---------------------------------------------------------------- 数据模型


class UploadResponse(BaseModel):
    doc_name: str
    chunks: int


class DocInfo(BaseModel):
    doc_name: str
    chunks: int
    pages: int


class AskRequest(BaseModel):
    question: str = Field(min_length=1, description="用户问题")
    top_k: int | None = Field(default=None, ge=1, le=20, description="检索条数，默认取配置")


class CitationOut(BaseModel):
    index: int
    doc_name: str
    page_no: int


class AskResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    elapsed_ms: int


# ---------------------------------------------------------------- 接口


@app.get("/health")
def health(store: VectorStore = Depends(get_store)) -> dict:
    return {
        "status": "ok",
        "chunks": store.count(),
        "llm_model": settings.llm_model,
        "embedding_model": settings.embedding_model,
    }


@app.post("/api/documents", response_model=UploadResponse)
def upload_document(
    file: UploadFile = File(...),
    store: VectorStore = Depends(get_store),
    embedder: Embedder = Depends(get_embedder),
) -> UploadResponse:
    """收文件 → 存盘 → 解析分块 → 向量化 → 入库。"""
    filename = file.filename or "unnamed"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIX:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型：{suffix or '(无后缀)'}")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)  # 分块拷贝，别一次性读进内存

    try:
        n = ingest_file(dest, embedder, store)
    except ParseError as exc:  # 解析器抛的已知错误 → 422，让调用方看得懂
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    logger.info("上传完成 | {} → {} 块", filename, n)
    return UploadResponse(doc_name=filename, chunks=n)


@app.get("/api/documents", response_model=list[DocInfo])
def list_documents(store: VectorStore = Depends(get_store)) -> list[DocInfo]:
    return [DocInfo(**item) for item in store.list_documents()]


@app.delete("/api/documents/{doc_name}")
def delete_document(doc_name: str, store: VectorStore = Depends(get_store)) -> dict:
    store.delete_document(doc_name)
    logger.info("删除文档 | {}", doc_name)
    return {"deleted": doc_name}


@app.post("/api/ask", response_model=AskResponse)
def ask(req: AskRequest, pipeline: QAPipeline = Depends(get_pipeline)) -> AskResponse:
    t0 = time.perf_counter()
    result = pipeline.ask(req.question, top_k=req.top_k)
    elapsed = int((time.perf_counter() - t0) * 1000)
    return AskResponse(
        answer=result.answer,
        citations=[
            CitationOut(index=c.index, doc_name=c.doc_name, page_no=c.page_no)
            for c in result.citations
        ],
        elapsed_ms=elapsed,
    )
