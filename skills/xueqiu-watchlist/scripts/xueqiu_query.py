#!/usr/bin/env python3
"""
雪球关注列表查询工具
"""
import csv
import json
import sys
from pathlib import Path

# Windows控制台utf-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass


def parse_watchlist_csv(file_path: str):
    """解析关注列表CSV"""
    records = []
    
    with open(file_path, "r", encoding="utf-8-sig") as f:
        content = f.read().strip()
        
        # 尝试JSON格式
        if content.startswith("["):
            try:
                return json.loads(content)
            except:
                pass
        
        # 尝试CSV格式
        lines = content.split("\n")
        if len(lines) > 1:
            # 检查是否有表头
            first_line = lines[0]
            if "," in first_line and any(k in first_line for k in ["代码", "名称", "code", "name"]):
                # 有表头的CSV
                reader = csv.DictReader(f)
                for row in reader:
                    code = row.get("代码") or row.get("code") or ""
                    name = row.get("名称") or row.get("name") or ""
                    industry = row.get("行业") or row.get("industry") or ""
                    note = row.get("备注") or row.get("note") or ""
                    
                    if code:
                        records.append({
                            "code": code,
                            "name": name,
                            "industry": industry,
                            "note": note
                        })
            else:
                # 无表头，每行一个代码
                for line in lines:
                    code = line.strip()
                    if code and (code.isdigit() or code.startswith("6")):
                        records.append({"code": code, "name": "", "industry": "", "note": ""})
    
    return records


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="雪球关注列表查询")
    parser.add_argument("--file", required=True, help="关注列表CSV文件路径")
    parser.add_argument("--export", help="导出JSON路径")
    parser.add_argument("--list", action="store_true", help="显示列表")
    
    args = parser.parse_args()
    
    # 解析CSV
    records = parse_watchlist_csv(args.file)
    print(f"解析完成: {len(records)} 只股票")
    
    if args.list:
        print(f"\n关注列表")
        print(f"=" * 40)
        for r in records:
            print(f"{r['code']} {r['name']} {r['industry']} {r['note']}")
    
    if args.export:
        with open(args.export, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        print(f"导出完成: {args.export}")


if __name__ == "__main__":
    main()
