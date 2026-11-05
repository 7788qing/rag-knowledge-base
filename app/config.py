"""全局配置中心：所有可调参数集中在这里，从 .env 文件读取。

设计要点：
  1. 「改参数不改代码」——调 chunk_size / top_k 只动 .env，重启即生效；
  2. 密钥（DASHSCOPE_API_KEY）永远不写死在代码里，.gitignore 已排除 .env；
  3. pydantic-settings 会做类型校验：.env 里写 CHUNK_SIZE=abc 会直接报错，
     而不是等到运行时才发现是字符串。
"""
from pathlib import Path

from pydantic_settings import BaseSettings

# 项目根目录：app/config.py → 上两级 → rag-knowledge-base/
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # ---- LLM：通义千问（DashScope 的 OpenAI 兼容模式）----
    dashscope_api_key: str = ""  # 必须在 .env 中填写
    llm_model: str = "qwen-plus"
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # ---- Embedding ----
    embedding_provider: str = "dashscope"  # dashscope=云端API（默认，零显卡要求）；local=本地BGE（需 torch）
    embedding_model: str = "text-embedding-v4"  # 云端模型名；切 local 模式时改回 "BAAI/bge-large-zh-v1.5"
    embedding_device: str = "cpu"  # 仅 local 模式用；有 NVIDIA 显卡可改 "cuda"

    # ---- 分块 ----
    chunk_size: int = 500  # 字符数；BGE-Large 最佳输入约 512 token
    chunk_overlap: int = 80  # 约 16% 重叠，缓解句子被拦腰截断

    # ---- 检索 ----
    top_k: int = 5

    # ---- 路径 ----
    data_dir: Path = BASE_DIR / "data"
    chroma_dir: Path = BASE_DIR / "data" / "chroma"

    model_config = {
        "env_file": BASE_DIR / ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# 模块级单例：全项目 from app.config import settings 共享同一份配置
settings = Settings()
