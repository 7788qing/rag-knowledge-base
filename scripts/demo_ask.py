"""最小可跑脚本：入库示例文档 → 提问 → 打印答案和引用。

用法（先在 .env 里填好 LLM_API_KEY 和 EMBEDDING_API_KEY）：
    python scripts/demo_ask.py
    python scripts/demo_ask.py "迟到怎么算？"

分工：
  对话（回答问题）= DeepSeek
  向量（把文字变数字）= 硅基流动 bge-m3（免费）
  会用掉少量额度，基本在免费范围内。
"""
import sys
from pathlib import Path

# 让脚本在项目根目录或 scripts/ 目录下运行都能找到 app 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.rag.embedder import build_embedder
from app.rag.llm import OpenAICompatChat
from app.rag.qa import QAPipeline
from app.rag.vector_store import VectorStore, ingest_file

SAMPLE_DOC = "data/raw/员工手册.md"

MISSING_HINT = """还缺 API key。

请在项目根目录新建 .env 文件，填这两行（可参考 .env.example）：

  LLM_API_KEY=sk-你的DeepSeek密钥
  EMBEDDING_API_KEY=sk-你的硅基流动密钥

说明：
  LLM_API_KEY        去 https://platform.deepseek.com/api_keys 拿（你已有）
  EMBEDDING_API_KEY  去 https://cloud.siliconflow.cn 注册后拿（bge-m3 免费）
"""


def main() -> None:
    missing = []
    if not settings.llm_api_key:
        missing.append("LLM_API_KEY")
    if not settings.embedding_api_key:
        missing.append("EMBEDDING_API_KEY")
    if missing:
        print(MISSING_HINT)
        print("当前缺少：" + "、".join(missing))
        sys.exit(1)

    store = VectorStore()
    if store.count() == 0:
        print(f"库是空的，先入库示例文档：{SAMPLE_DOC}")
        n = ingest_file(SAMPLE_DOC, build_embedder(), store)
        print(f"已入库 {n} 块")

    question = sys.argv[1] if len(sys.argv) > 1 else "迟到怎么算？"
    pipeline = QAPipeline(store, build_embedder(), OpenAICompatChat())
    result = pipeline.ask(question)

    print(f"\n问题：{result.question}")
    print(f"回答：{result.answer}")
    if result.citations:
        print("\n来源：")
        for c in result.citations:
            print(f"  [{c.index}] {c.doc_name} 第{c.page_no}页")


if __name__ == "__main__":
    main()
