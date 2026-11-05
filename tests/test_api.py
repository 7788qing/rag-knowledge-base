"""接口层测试：TestClient + 假实现（FakeEmbedder / FakeChat），不联网。

关键手法：dependency_overrides。
FastAPI 通过 Depends 拿工具，测试里把「拿工具的函数」换掉，
接口代码一行不用改，就能跑在假环境里。
"""
import pytest
from fastapi.testclient import TestClient

import app.main as api
from app.main import app, get_embedder, get_llm, get_pipeline, get_store
from app.rag.embedder import FakeEmbedder
from app.rag.llm import FakeChat
from app.rag.qa import QAPipeline
from app.rag.vector_store import VectorStore

FAKE_ANSWER = "迟到超过 30 分钟按事假半天处理[1]。"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """每个测试一个干净库 + 假模型 + 临时上传目录。"""
    monkeypatch.setattr(api, "UPLOAD_DIR", tmp_path / "uploads")

    store = VectorStore(persist_dir=tmp_path / "chroma")
    embedder = FakeEmbedder()
    llm = FakeChat(FAKE_ANSWER)

    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_embedder] = lambda: embedder
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_pipeline] = lambda: QAPipeline(store, embedder, llm)

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["chunks"] == 0


def test_upload_and_list(client):
    content = "# 员工手册\n\n## 考勤\n\n迟到超过 30 分钟按事假半天处理。\n"
    resp = client.post(
        "/api/documents",
        files={"file": ("员工手册.md", content.encode("utf-8"), "text/markdown")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["doc_name"] == "员工手册.md"
    assert body["chunks"] >= 1

    docs = client.get("/api/documents").json()
    assert len(docs) == 1
    assert docs[0]["doc_name"] == "员工手册.md"
    assert docs[0]["chunks"] == body["chunks"]


def test_upload_rejects_unsupported_type(client):
    resp = client.post(
        "/api/documents",
        files={"file": ("病毒.exe", b"binary", "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_ask_returns_answer_with_citation(client):
    content = "# 员工手册\n\n## 考勤\n\n迟到超过 30 分钟按事假半天处理。\n"
    client.post(
        "/api/documents",
        files={"file": ("员工手册.md", content.encode("utf-8"), "text/markdown")},
    )

    resp = client.post("/api/ask", json={"question": "迟到怎么算？", "top_k": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert "事假" in body["answer"]
    assert len(body["citations"]) == 1
    assert body["citations"][0]["doc_name"] == "员工手册.md"
    assert body["elapsed_ms"] >= 0


def test_ask_on_empty_store(client):
    resp = client.post("/api/ask", json={"question": "库是空的会怎样"})
    assert resp.status_code == 200
    assert resp.json()["citations"] == []


def test_delete_document(client):
    content = "# 手册\n\n正文内容若干。\n"
    client.post(
        "/api/documents",
        files={"file": ("临时.md", content.encode("utf-8"), "text/markdown")},
    )
    assert len(client.get("/api/documents").json()) == 1

    resp = client.delete("/api/documents/临时.md")
    assert resp.status_code == 200
    assert client.get("/api/documents").json() == []
    assert client.get("/health").json()["chunks"] == 0
