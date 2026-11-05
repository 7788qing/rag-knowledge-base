"""Prompt 组装：把检索到的片段编号，塞进给模型的问题里。

引用编号协议（本项目最关键的设计之一）：
  片段 [1] [2] [3] … → 要求模型在结论后标 [n]
  → 后处理把 [n] 映射回「文档名 + 页码」
  这就是「答案附带来源引用」的实现方式，也是防幻觉的第一道闸门。
"""

SYSTEM_PROMPT = """你是企业知识库问答助手。请严格按以下规则回答：

1. 只使用【资料】里的内容回答，不要使用你自己的知识，不要编造。
2. 每个结论后面用 [编号] 标注来源，可以标多个，如 [1][3]。
3. 如果资料不足以回答，直接说「资料中没有相关信息」，不要猜测。
4. 用中文回答，简洁清楚，不要大段照抄资料原文。
"""


def build_context(hits: list[dict]) -> str:
    """把检索结果拼成带编号的资料块。"""
    blocks: list[str] = []
    for i, hit in enumerate(hits, start=1):
        blocks.append(f"[{i}] 来源：{hit['doc_name']} 第{hit['page_no']}页\n{hit['text']}")
    return "\n\n".join(blocks)


def build_messages(question: str, hits: list[dict]) -> list[dict]:
    """组装 chat 接口要的 messages 格式：一条 system 规则 + 一条 user 资料+问题。"""
    user_content = f"【资料】\n{build_context(hits)}\n\n【问题】\n{question}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
