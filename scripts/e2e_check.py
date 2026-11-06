"""端到端边界测试：找 bug 用的。跑完输出 PASS/FAIL 清单。"""
import concurrent.futures as cf
import json

import httpx

BASE = "http://127.0.0.1:8000"
results = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((ok, name, detail))
    print(f"{'PASS' if ok else 'FAIL'} | {name} | {detail}")


def ask(question: str, top_k: int | None = None, timeout: float = 120.0):
    payload = {"question": question}
    if top_k is not None:
        payload["top_k"] = top_k
    return httpx.post(f"{BASE}/api/ask", json=payload, timeout=timeout)


print("=" * 70)
print("1. 基础健康检查")
r = httpx.get(f"{BASE}/health", timeout=30)
check("GET /health 返回 200", r.status_code == 200, r.text[:80])

print("\n2. 参数校验（期望全部 422）")
for name, payload in [
    ("空问题", {"question": ""}),
    ("缺 question 字段", {}),
    ("question 不是字符串", {"question": 123}),
    ("top_k=0", {"question": "年假", "top_k": 0}),
    ("top_k=21", {"question": "年假", "top_k": 21}),
]:
    r = httpx.post(f"{BASE}/api/ask", json=payload, timeout=60)
    check(f"{name} 应 422", r.status_code == 422, f"实际 {r.status_code}")

print("\n3. 检索与生成")
r = ask("公司有没有团建经费？")
d = r.json()
check("团建问题返回 200", r.status_code == 200, f"耗时 {d.get('elapsed_ms')}ms")
check("团建问题有引用", len(d.get("citations", [])) > 0, json.dumps(d.get("citations"), ensure_ascii=False)[:120])

r = ask("今天北京的天气怎么样？")
d = r.json()
no_hallucination = ("没有相关" in d["answer"]) or ("未提及" in d["answer"]) or not d["citations"]
check("无关问题不瞎编", no_hallucination, d["answer"][:70])

r = ask("公司" * 800)  # 1600 字超长问题
check("超长问题（1600 字）不崩溃", r.status_code in (200, 422), f"状态 {r.status_code}")

print("\n4. 上传接口边界")
r = httpx.post(f"{BASE}/api/documents", files={"file": ("virus.exe", b"MZ", "application/octet-stream")}, timeout=60)
check("exe 文件应 400", r.status_code == 400, f"实际 {r.status_code}")

r = httpx.post(f"{BASE}/api/documents", files={"file": ("empty.md", b"", "text/markdown")}, timeout=60)
check("空文件不产生脏数据", r.status_code in (200, 400, 422), f"{r.status_code} {r.text[:60]}")

r = httpx.post(f"{BASE}/api/documents", files={"file": ("noext", b"# hi", "text/plain")}, timeout=60)
check("无后缀文件应 400", r.status_code == 400, f"实际 {r.status_code}")

print("\n5. 幂等性：同一文件上传两次")
content = "# 测试文档\n\n## 第一节\n\n这是用于幂等测试的内容，包含唯一标记 ALPHA-7788。\n"
r1 = httpx.post(f"{BASE}/api/documents", files={"file": ("_test_dup.md", content.encode(), "text/markdown")}, timeout=120)
n1 = r1.json()["chunks"] if r1.status_code == 200 else -1
r2 = httpx.post(f"{BASE}/api/documents", files={"file": ("_test_dup.md", content.encode(), "text/markdown")}, timeout=120)
n2 = r2.json()["chunks"] if r2.status_code == 200 else -1
docs = httpx.get(f"{BASE}/api/documents", timeout=30).json()
dup = [x for x in docs if x["doc_name"] == "_test_dup.md"]
check("重复上传不翻倍", len(dup) == 1 and dup[0]["chunks"] == n1, f"第一次 {n1} 块，第二次 {n2} 块，库内 {dup}")

print("\n6. 删除接口")
r = httpx.delete(f"{BASE}/api/documents/_test_dup.md", timeout=30)
docs = httpx.get(f"{BASE}/api/documents", timeout=30).json()
check("删除测试文档", r.status_code == 200 and all(x["doc_name"] != "_test_dup.md" for x in docs), f"状态 {r.status_code}")
r = httpx.delete(f"{BASE}/api/documents/根本不存在.md", timeout=30)
check("删除不存在的文档不报 500", r.status_code < 500, f"实际 {r.status_code}")

print("\n7. 并发")
qs = ["年假有多少天？", "迟到怎么处理？", "报销时限是多久？", "竞业限制补偿多少？", "专利奖励多少？"]
with cf.ThreadPoolExecutor(max_workers=5) as ex:
    codes = list(ex.map(lambda q: ask(q, timeout=180).status_code, qs))
check("5 个并发提问全部成功", all(c == 200 for c in codes), f"状态码 {codes}")

print("\n8. 最终状态")
h = httpx.get(f"{BASE}/health", timeout=30).json()
docs = httpx.get(f"{BASE}/api/documents", timeout=30).json()
check("库内无残留测试数据", all(not x["doc_name"].startswith("_test") and x["doc_name"] != "empty.md" for x in docs), json.dumps(docs, ensure_ascii=False))
check("块数正常（约 91）", 85 <= h["chunks"] <= 120, f"chunks={h['chunks']}")

print("\n" + "=" * 70)
failed = [x for x in results if not x[0]]
print(f"共 {len(results)} 项，通过 {len(results) - len(failed)}，失败 {len(failed)}")
for _, name, detail in failed:
    print(f"  失败：{name} | {detail}")
