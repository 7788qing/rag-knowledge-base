"""Streamlit 前端：两个页面（知识问答 / 文档管理）。

它自己不碰数据库、不碰模型，只做一件事：**调 FastAPI 接口**。
好处：前后端分离，以后换成 Vue/React 也不用动后端。

启动（先确保后端已在跑）：
    终端1: python -m uvicorn app.main:app --reload
    终端2: streamlit run app/ui/app.py
"""
import os

import httpx
import streamlit as st

# 后端地址：默认本机 8000，部署到服务器时可用环境变量覆盖
API = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
TIMEOUT = 180.0  # 上传大文件、等模型回答，都要留足时间

st.set_page_config(page_title="私有知识库问答", page_icon="📚", layout="wide")


# ---------------------------------------------------------------- 薄薄的 HTTP 封装


def api_get(path: str):
    return httpx.get(f"{API}{path}", timeout=TIMEOUT)


def api_post(path: str, json: dict | None = None, files: dict | None = None):
    return httpx.post(f"{API}{path}", json=json, files=files, timeout=TIMEOUT)


def api_delete(path: str):
    return httpx.delete(f"{API}{path}", timeout=TIMEOUT)


def fetch_health() -> dict | None:
    """拿服务状态；连不上就返回 None，不抛异常（前端不应该崩）。"""
    try:
        resp = api_get("/health")
        return resp.json() if resp.status_code == 200 else None
    except httpx.HTTPError:
        return None


# ---------------------------------------------------------------- 侧边栏：状态


with st.sidebar:
    st.title("📚 知识库问答")
    st.caption("上传文档 → 提问 → 带来源回答")
    st.divider()

    health = fetch_health()
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


# ---------------------------------------------------------------- 两个页签

tab_ask, tab_docs = st.tabs(["💬 知识问答", "📁 文档管理"])


# ---------------------------------------------------------------- 页签一：问答

with tab_ask:
    st.subheader("问点什么")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # 把历史消息重绘一遍（Streamlit 每次交互都会重跑整个脚本）
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            for cite in msg.get("citations", []):
                st.caption(f"[{cite['index']}] {cite['doc_name']} · 第{cite['page_no']}页")

    question = st.chat_input("例如：迟到怎么算？")

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
                for cite in data["citations"]:
                    st.caption(f"[{cite['index']}] {cite['doc_name']} · 第{cite['page_no']}页")
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


# ---------------------------------------------------------------- 页签二：文档管理

with tab_docs:
    st.subheader("上传文档")
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
    st.subheader("已有文档")

    try:
        docs = api_get("/api/documents").json() if health else []
    except httpx.HTTPError:
        docs = []

    if not docs:
        st.info("知识库还是空的，先上传一份文档。")
    else:
        head = st.columns([5, 2, 2, 2])
        head[0].markdown("**文件名**")
        head[1].markdown("**块数**")
        head[2].markdown("**页数**")
        head[3].markdown("**操作**")

        for doc in docs:
            c1, c2, c3, c4 = st.columns([5, 2, 2, 2])
            c1.write(doc["doc_name"])
            c2.write(str(doc["chunks"]))
            c3.write(str(doc["pages"]))
            if c4.button("删除", key=f"del::{doc['doc_name']}"):
                api_delete(f"/api/documents/{doc['doc_name']}")
                st.rerun()
