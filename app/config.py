"""全局配置中心：所有可调参数集中在这里，从 .env 文件读取。

设计要点：
  1. 「改参数不改代码」——调 chunk_size / top_k 只动 .env，重启即生效；
  2. 密钥（LLM_API_KEY / EMBEDDING_API_KEY）永远不写死在代码里，.gitignore 已排除 .env；
  3. pydantic-settings 会做类型校验：.env 里写 CHUNK_SIZE=abc 会直接报错，
     而不是等到运行时才发现是字符串。
"""
from pathlib import Path

from pydantic_settings import BaseSettings

# 项目根目录：app/config.py → 上两级 → rag-knowledge-base/
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # ---- 对话模型（负责回答问题的那个）----
    # 只要求「兼容 OpenAI 格式」：DeepSeek / 通义 / 智谱 / OpenAI / Ollama 都能用。
    # 换平台只改这三行，代码一个字不动。
    llm_api_key: str = ""                                  # 在 .env 里填，绝不写进代码
    llm_base_url: str = "https://api.deepseek.com/v1"      # DeepSeek 官方地址
    llm_model: str = "deepseek-flash"                      # 若报「模型不存在」，改试 deepseek-chat

    # ---- 向量模型（把文字变成数字的那个）----
    # 注意：DeepSeek 没有 embedding 接口，所以要单独配一家。
    # 默认硅基流动的 bge-m3：免费、中文效果好、OpenAI 兼容。
    embedding_provider: str = "openai_compat"              # openai_compat=任意兼容服务；fake=测试用
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"                   # 1024 维；模型名必须带 BAAI/ 前缀
    embedding_device: str = "cpu"                          # 本地模式预留，云端用不到

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
