# 私有知识库 RAG 问答系统

企业内部文档智能问答：上传 PDF / Word / Markdown → 分块向量化入库 → 提问检索 → 大模型生成带来源引用的答案。

## 技术栈

FastAPI · LangChain · PyMuPDF / python-docx · Chroma · bge-m3（硅基流动）· DeepSeek · Streamlit · Docker

> 两个模型都走「OpenAI 兼容」接口，换平台只改 `.env` 三行，代码不动。

## 快速开始

```bash
# 1. 虚拟环境（本项目用 Python 3.13；3.15 装不上 numpy/chromadb）
py -3.13 -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate    # macOS / Linux

# 2. 安装依赖（pip 走清华镜像，官方源会很慢）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 3. 配置
copy .env.example .env         # 填 LLM_API_KEY（DeepSeek）+ EMBEDDING_API_KEY（硅基流动）

# 4. 测试
python -m pytest

# 5. 跑一次真实问答（会用到云端额度）
python scripts/demo_ask.py
```

## 项目阶段

- **阶段1（基础版）**：上传→解析→分块→向量化→检索→带引用问答 → Web 交互 + RESTful 接口
- **阶段2（优化版）**：混合检索(BM25+向量,RRF) · Rerank 重排 · HyDE 查询改写 · 会话记忆 · 检索评估(Recall@K/MRR)
- **阶段3（生产化）**：Milvus/pgvector · OCR · 权限隔离 · Langfuse 观测

详细设计见 `docs/架构设计方案.md`。
