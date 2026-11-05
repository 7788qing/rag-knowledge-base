"""交互式填写 API key：按提示粘贴两个 key，自动校验并写入 .env。

用法（在项目根目录、已激活 .venv 的终端里）：
    python scripts/setup_keys.py

流程：
  1. 粘贴 DeepSeek key → 自动连服务器验证
  2. 粘贴硅基流动 key → 自动验证
  3. 两个都通过就写入 .env
"""
import re
import sys
from pathlib import Path

# 让脚本能找到 app 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import BASE_DIR

ENV_PATH = BASE_DIR / ".env"

DEEPSEEK_URL = "https://api.deepseek.com/v1"
SILICONFLOW_URL = "https://api.siliconflow.cn/v1"


def write_env(key: str, value: str) -> None:
    """把 .env 里 KEY=... 那一行换成新值；没有这一行就追加。"""
    text = ENV_PATH.read_text(encoding="utf-8")
    pattern = rf"^{key}=.*$"
    line = f"{key}={value}"
    if re.search(pattern, text, flags=re.M):
        text = re.sub(pattern, line, text, flags=re.M)
    else:
        text = text.rstrip() + "\n" + line + "\n"
    ENV_PATH.write_text(text, encoding="utf-8")


def list_models(base_url: str, key: str) -> list[str]:
    """最轻量的验证：只请求模型列表，不消耗生成额度。"""
    from openai import OpenAI

    client = OpenAI(api_key=key, base_url=base_url, timeout=30)
    return [m.id for m in client.models.list().data]


def ask_key(label: str) -> str:
    """反复提示，直到拿到一个非空的 key。"""
    while True:
        raw = input(f"\n请粘贴你的 {label}（粘贴后按回车）：").strip().strip('"').strip("'")
        if raw:
            return raw
        print("  没读到内容，请重新粘贴。")


def main() -> None:
    print("=" * 46)
    print("API key 配置助手")
    print("=" * 46)

    # ---- 第 1 步：DeepSeek ----
    while True:
        llm_key = ask_key("DeepSeek key")
        try:
            models = list_models(DEEPSEEK_URL, llm_key)
            print(f"  ✔ DeepSeek 连接成功，可用模型：{', '.join(models[:4])}")
            break
        except Exception as exc:
            print(f"  ✖ 连不上：{exc}")
            print("    检查：key 有没有复制全？是不是在 platform.deepseek.com 新建的？")

    # ---- 第 2 步：硅基流动 ----
    while True:
        emb_key = ask_key("硅基流动 key")
        try:
            models = list_models(SILICONFLOW_URL, emb_key)
            print(f"  ✔ 硅基流动连接成功，可用模型 {len(models)} 个")
            break
        except Exception as exc:
            print(f"  ✖ 连不上：{exc}")
            print("    检查：key 有没有复制全？账号是否完成实名？")

    # ---- 第 3 步：写入 .env ----
    write_env("LLM_API_KEY", llm_key)
    write_env("EMBEDDING_API_KEY", emb_key)
    print("\n✔ 已写入 .env")
    print("\n下一步，跑真实问答：")
    print("    python scripts/demo_ask.py")


if __name__ == "__main__":
    main()
