"""Streamlit 前端：知识问答 + 文档管理。

它自己不碰数据库、不碰模型，只做一件事：调 FastAPI 接口。
启动：
    终端1: python -m uvicorn app.main:app --reload
    终端2: streamlit run app/ui/app.py
"""
import os

import httpx
import streamlit as st

API = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
TIMEOUT = 180.0

st.set_page_config(page_title="私有知识库问答", page_icon="📚", layout="wide")

# ---------------------------------------------------------------- 外观

CUSTOM_CSS = """
<style>
.block-container { max-width: 1080px; padding-top: 2rem; padding-bottom: 3rem; }

.hero {
  background: linear-gradient(135deg, #2563EB 0%, #6D28D9 100%);
  border-radius: 18px;
  padding: 26px 30px;
  margin-bottom: 22px;
  color: #FFFFFF;
}
.hero-title { font-size: 24px; font-weight: 600; margin: 0 0 6px; letter-spacing: .3px; }
.hero-sub { font-size: 13.5px; margin: 0; color: rgba(255,255,255,.86); }
.hero-chips { margin-top: 14px; }
.hero-chip {
  display: inline-block; font-size: 12px; padding: 4px 11px; margin-right: 8px;
  border-radius: 999px; background: rgba(255,255,255,.18); color: #fff;
}

[data-testid="stChatMessage"] {
  background: #FFFFFF;
  border: 1px solid #E6ECF5;
  border-radius: 14px;
  padding: 14px 18px;
  margin-bottom: 10px;
  box-shadow: 0 1px 3px rgba(16,24,40,.05);
}

.cite {
  display: inline-block;
  background: #EFF6FF;
  color: #1D4ED8;
  border: 1px solid #DBEAFE;
  border-radius: 999px;
  padding: 2px 10px;
  font-size: 12px;
  margin: 6px 6px 0 0;
}

[data-testid="stMetric"] {
  background: #FFFFFF;
  border: 1px solid #E6ECF5;
  border-radius: 14px;
  padding: 12px 14px;
}

[data-testid="stFileUploaderDropzone"], [data-testid="stFileUploader"] section {
  border: 1.5px dashed #C9D8EC;
  border-radius: 14px;
  background: #FAFCFF;
}

.stButton > button {
  border-radius: 10px;
  border: 1px solid #D9E2F0;
  font-weight: 500;
}
.stButton > button[kind="primary"] {
  background: linear-gradient(135deg, #2563EB, #4F46E5);
  border: none;
  color: #fff;
}

.doc-card {
  background: #FFFFFF;
  border: 1px solid #E6ECF5;
  border-radius: 14px;
  padding: 14px 18px;
  margin-bottom: 10px;
}
.doc-name { font-weight: 500; color: #111827; font-size: 14.5px; }
.doc-meta { color: #6B7280; font-size: 12.5px; margin-top: 2px; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------- HTTP 封装


def api_get(path: str):
    return httpx.get(f"{API}{path}", timeout=TIMEOUT)


def api_post(path: str, json: dict | None = None, files: dict | None = None):
    return httpx.post(f"{API}{path}", json=json, files=files, timeout=TIMEOUT)


def api_delete(path: str):
    return httpx.delete(f"{API}{path}", timeout=TIMEOUT)


def fetch_health() -> dict | None:
    """拿服务状态；连不上返回 None，不让前端崩。"""
    try:
        resp = api_get("/health")
        return resp.json() if resp.status_code == 200 else None
    except httpx.HTTPError:
        return None


def render_citations(citations: list[dict]) -> None:
    """引用做成小标签，比一行纯文字好看也好读。"""
    html = "".join(
        f'<span class="cite">[{c["index"]}] {c["doc_name"]} · 第{c["page_no"]}页</span>'
        for c in citations
    )
    if html:
        st.markdown(html, unsafe_allow_html=True)


# ---------------------------------------------------------------- 顶部标题

health = fetch_health()
chunk_total = health["chunks"] if health else 0
model_name = health["llm_model"] if health else "未连接"

st.markdown(
    f"""
    <div class="hero">
      <p class="hero-title">私有知识库 · 智能问答</p>
      <p class="hero-sub">上传企业文档，用自然语言提问，答案附带原文出处</p>
      <div class="hero-chips">
        <span class="hero-chip">已入库 {chunk_total} 块</span>
        <span class="hero-chip">模型 {model_name}</span>
        <span class="hero-chip">检索 + 引用溯源</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------- 侧边栏

with st.sidebar:
    st.markdown("### 服务状态")
    if health:
        st.success("后端已连接")
        st.metric("已入库块数", health["chunks"])
        st.caption(f"对话模型 · {health['llm_model']}")
        st.caption(f"向量模型 · {health['embedding_model']}")
    else:
        st.error("连不上后端")
        st.code("python -m uvicorn app.main:app --reload", language="bash")
        st.caption("先跑起后端，再刷新本页")

    st.divider()
    if st.button("清空对话", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.caption("阶段 1 基础版 · FastAPI + Chroma + DeepSeek")


# ---------------------------------------------------------------- 两个页签

tab_ask, tab_docs = st.tabs(["知识问答", "文档管理"])


with tab_ask:
    if "messages" not in st.session_state:
        st.session_state.messages = []

    if not st.session_state.messages:
        st.info("试试问：年假有多少天？ / 迟到怎么算？ / 报销要在几天内提交？")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            render_citations(msg.get("citations", []))

    question = st.chat_input("输入你的问题…")

    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("检索资料、生成回答中…"):
                try:
                    resp = api_post("/api/ask", json={"question": question})
                except httpx.HTTPError as exc:
                    st.error(f"请求失败：{exc}")
                    resp = None

            if resp is not None and resp.status_code == 200:
                data = resp.json()
                st.markdown(data["answer"])
                render_citations(data["citations"])
                st.caption(f"耗时 {data['elapsed_ms']} ms")

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": data["answer"],
                        "citations": data["citations"],
                    }
                )
            elif resp is not None:
                st.error(f"接口返回 {resp.status_code}：{resp.text}")


with tab_docs:
    st.markdown("#### 上传文档")
    st.caption("支持 PDF / Word(.docx) / Markdown / TXT，单次一个文件")

    uploaded = st.file_uploader(
        "选择文件", type=["pdf", "docx", "md", "markdown", "txt"], label_visibility="collapsed"
    )

    if uploaded is not None and st.button("上传并入库", type="primary"):
        with st.spinner("解析 → 分块 → 向量化入库…"):
            files = {
                "file": (
                    uploaded.name,
                    uploaded.getvalue(),
                    uploaded.type or "application/octet-stream",
                )
            }
            try:
                resp = api_post("/api/documents", files=files)
            except httpx.HTTPError as exc:
                st.error(f"请求失败：{exc}")
                resp = None

        if resp is not None and resp.status_code == 200:
            data = resp.json()
            st.success(f"入库成功：{data['doc_name']}，共 {data['chunks']} 块")
            st.rerun()
        elif resp is not None:
            st.error(f"入库失败（{resp.status_code}）：{resp.text}")

    st.divider()
    st.markdown("#### 已有文档")

    try:
        docs = api_get("/api/documents").json() if health else []
    except httpx.HTTPError:
        docs = []

    if not docs:
        st.info("知识库还是空的，先上传一份文档。")
    else:
        for doc in docs:
            c1, c2 = st.columns([8, 1])
            with c1:
                st.markdown(
                    f'<div class="doc-card"><div class="doc-name">{doc["doc_name"]}</div>'
                    f'<div class="doc-meta">{doc["chunks"]} 块 · {doc["pages"]} 页</div></div>',
                    unsafe_allow_html=True,
                )
            with c2:
                st.write("")
                if st.button("删除", key=f"del::{doc['doc_name']}"):
                    api_delete(f"/api/documents/{doc['doc_name']}")
                    st.rerun()
