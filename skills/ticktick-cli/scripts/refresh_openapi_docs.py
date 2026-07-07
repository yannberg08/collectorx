#!/usr/bin/env python3
"""刷新本地 dida365 OpenAPI 文档副本。

用法：
  python3 refresh_openapi_docs.py            # 抓最新文档，列所有 endpoint
  python3 refresh_openapi_docs.py --update   # 同上 + 覆盖 references/dida365-openapi.md

为什么要这个：
  dida365 的 Open API 文档 https://developer.dida365.com/docs/index.html#/openapi
  是 SPA（JS 渲染），普通 curl/wget 拉不到内容。本地 references/dida365-openapi.md
  曾经手抓过一份，但漏了 task/completed、task/filter、task/move、focus、habit 等 endpoint。

  这个脚本用 Playwright 自动渲染 SPA，把完整文档抓下来，方便维护。
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

URL = "https://developer.dida365.com/docs/index.html#/openapi"
DOC_PATH = Path(__file__).resolve().parent.parent / "references" / "dida365-openapi.md"


def scrape() -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("请先安装 playwright: pip3 install playwright && playwright install chromium")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        text = page.locator("body").inner_text()
        browser.close()
    return text


def list_endpoints(text: str) -> list[tuple[str, str]]:
    """从抓到的文字里提取 (method, path) 列表，去重。"""
    seen = set()
    out: list[tuple[str, str]] = []
    for m in re.finditer(r"(GET|POST|PUT|DELETE|PATCH)\s+(/[a-zA-Z0-9_/\-{}]+)", text):
        method = m.group(1)
        # 把 {{var}} 双花括号统一成单花括号
        path = re.sub(r"\{\{(\w+)\}\}", r"{\1}", m.group(2))
        key = (method, path)
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update", action="store_true", help="覆盖写入 references/dida365-openapi.md")
    ap.add_argument("--section", help="只显示包含此关键词的章节（如 'Filter Tasks'）")
    args = ap.parse_args()

    print(f"抓取 {URL} ...")
    text = scrape()
    print(f"  拿到 {len(text)} 字符\n")

    endpoints = list_endpoints(text)
    print(f"📋 共 {len(endpoints)} 个 endpoint：")
    for method, path in endpoints:
        print(f"  {method:6} {path}")

    if args.section:
        idx = text.find(args.section)
        if idx >= 0:
            print(f"\n=== {args.section} ===")
            print(text[idx : idx + 2500])
        else:
            print(f"\n⚠️ 没找到章节: {args.section}")

    if args.update:
        DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
        # 简单写法：把抓到的纯文本作为 md 内容（保留原结构）
        DOC_PATH.write_text(
            "# Dida365 Open API（自动抓取）\n\n"
            f"来源：{URL}\n来源 SPA 抓取于 {Path(__file__).name}\n\n"
            "---\n\n"
            + text,
            encoding="utf-8",
        )
        print(f"\n✅ 已覆盖 {DOC_PATH}")


if __name__ == "__main__":
    main()
