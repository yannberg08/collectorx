#!/usr/bin/env python3
"""
雪球关注列表查询工具
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from xueqiu.parser import parse_watchlist_csv

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass


def main():
    parser = argparse.ArgumentParser(description="雪球关注列表查询")
    parser.add_argument("--file", required=True, help="关注列表CSV文件路径")
    parser.add_argument("--export", help="导出JSON路径")
    parser.add_argument("--list", action="store_true", help="显示列表")
    
    args = parser.parse_args()
    
    records = parse_watchlist_csv(args.file)
    print(f"解析完成: {len(records)} 只股票")
    
    if args.list:
        print(f"\n关注列表")
        print("=" * 40)
        for r in records:
            print(f"{r["code"]} {r["name"]} {r["industry"]} {r["note"]}")
    
    if args.export:
        with open(args.export, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        print(f"导出完成: {args.export}")


if __name__ == "__main__":
    main()
