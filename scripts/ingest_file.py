"""把本地文件直接灌进知识库（走 FastAPI 接口）。

用法：
    python scripts/ingest_file.py data/raw/新制度.md
    python scripts/ingest_file.py data/raw/新制度.md --replace 员工手册.md

参数：
    path        本地文件路径
    --replace   先删除这个文件名的旧文档（同名覆盖也能自动处理，这个参数用于换名字的场景）
"""
import argparse
import os
import sys
import time
from pathlib import Path

import httpx

BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
TIMEOUT = 600.0  # 大文件向量化可能较慢


def delete_doc(name: str) -> None:
    resp = httpx.delete(f"{BASE}/api/documents/{name}", timeout=TIMEOUT)
    if resp.status_code == 200:
        print(f"已删除旧文档：{name}")
    else:
        print(f"删除 {name} 失败（{resp.status_code}）：{resp.text}")


def upload(path: Path) -> dict:
    mime = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".md": "text/markdown",
        ".txt": "text/plain",
    }.get(path.suffix.lower(), "application/octet-stream")

    with path.open("rb") as f:
        files = {"file": (path.name, f.read(), mime)}
        resp = httpx.post(f"{BASE}/api/documents", files=files, timeout=TIMEOUT)

    if resp.status_code != 200:
        print(f"上传失败（{resp.status_code}）：{resp.text}")
        sys.exit(1)
    return resp.json()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="本地文件路径")
    parser.add_argument("--replace", help="先删除这个文件名的旧文档")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.is_file():
        print(f"文件不存在：{path}")
        sys.exit(1)

    print(f"文件：{path.name}（{path.stat().st_size / 1024:.1f} KB）")
    print(f"字数：{len(path.read_text(encoding='utf-8'))}")

    if args.replace:
        delete_doc(args.replace)

    t0 = time.perf_counter()
    data = upload(path)
    elapsed = time.perf_counter() - t0

    print(f"入库成功：{data['doc_name']}，共 {data['chunks']} 块，耗时 {elapsed:.1f} 秒")

    health = httpx.get(f"{BASE}/health", timeout=30).json()
    print(f"库内总块数：{health['chunks']}")
    docs = httpx.get(f"{BASE}/api/documents", timeout=30).json()
    print("当前文档：")
    for d in docs:
        print(f"  - {d['doc_name']}（{d['chunks']} 块 / {d['pages']} 页）")


if __name__ == "__main__":
    main()
